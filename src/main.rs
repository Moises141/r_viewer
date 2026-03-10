use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use clap::Parser;

mod cli;
mod config;
mod state;
mod error;
mod db;
mod eventlog;
pub mod server;

use quick_xml::Reader;
use quick_xml::events::Event;

use cli::{Cli, Commands, Channel, Level};
use config::Config;
use state::AppState;
use error::AppResult;
use db::models::EventRow;
use eventlog::client::EventLogClient;

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let config = Config::load(&cli).context("Failed to load configuration")?;

    println!("R_viewer starting");
    println!("Mode: {:?}", cli.command);
    println!("Database path: {}", config.db_path.display());

    match cli.command {
        Commands::Serve => {
            println!("Launching HTTP server on port {}", config.http_port);
            let state = AppState::new(config).await
                .context("Failed to initialize application state")?;
            
            let app = server::create_router(state);
            let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", 8080)).await.unwrap();
            
            println!("Listening on http://0.0.0.0:8080");
            axum::serve(listener, app).await.unwrap();
        }

        Commands::Ingest { channel, limit } => {
            println!("Ingesting up to {} events from channel: {}", limit, channel);

            let state = AppState::new(config).await
                .context("Failed to initialize application state")?;

            ingest_events(&state, &channel.to_string(), limit).await
                .context("Ingestion failed")?;
            println!("Ingestion complete");
        }

        Commands::Query { channel, level, limit } => {
            println!(
                "Querying events: channel={:?}, level={:?}, limit={}",
                channel, level, limit
            );

            let state = AppState::new(config).await
                .context("Failed to initialize application state")?;

            let events = query_events(&state, channel, level, limit, None).await
                .context("Query failed")?;

            print_events(&events);
        }

        Commands::Hello => {
            println!("R_viewer is running");
            println!("Available commands:");
            println!("  r_viewer ingest --channel System --limit 50");
            println!("  r_viewer query --level Error --limit 10");
            println!("  r_viewer serve");
        }
    }

    Ok(())
}

fn print_events(events: &[EventRow]) {
    if events.is_empty() {
        println!("No events found matching criteria");
        return;
    }

    println!("Found {} event(s)", events.len());
    println!("{:<19} | {:<8} | {:<19} | {:<6} | {}",
             "Time", "Level", "Source", "ID", "Message (truncated)");
    println!("{}", "-".repeat(100));

    for event in events {
        let msg_trunc: String = event.message.chars().take(80).collect();
        println!(
            "{} | {:<8} | {:<19} | {:<6} | {}",
            event.time.0.format("%Y-%m-%d %H:%M:%S"),
            event.level,
            event.source,
            event.event_id,
            msg_trunc.trim_end()
        );
    }
}

async fn ingest_events(state: &AppState, channel: &str, limit: usize) -> AppResult<()> {
    let inserted_count = ingest_events_logic(state, channel, limit).await?;
    println!("Successfully inserted {} parsed events into database", inserted_count);
    Ok(())
}

pub async fn ingest_events_logic(state: &AppState, channel: &str, limit: usize) -> AppResult<usize> {
    let db = state.db().await;

    let event_handles = unsafe {
        EventLogClient::query_channel(channel, None, limit)
            .context("Failed to query Windows Event Log channel")?
    };

    println!("Retrieved {} event handle(s) from channel '{}'", event_handles.len(), channel);

    let mut inserted_count = 0;

    for handle in event_handles {
        // Safe handle management: ensure handle is closed even if parsing or DB fails
        let _guard = scopeguard::guard(handle, |h| unsafe {
            EventLogClient::close_handle(h);
        });

        let result = process_single_event(handle, &db, channel).await;

        match result {
            Ok(true)  => inserted_count += 1,
            Ok(false) => {}
            Err(e)    => eprintln!("Failed to process event: {:#?}", e),
        }
    }

    Ok(inserted_count)
}

async fn process_single_event(
    handle: isize,
    db: &surrealdb::Surreal<surrealdb::engine::local::Db>,
    channel: &str,
) -> AppResult<bool> {
    let xml = unsafe {
        EventLogClient::render_event_xml(handle)
            .context("Failed to render event to XML")?
    };

    let row = parse_event_xml(&xml, channel)?;

    // Use the unique index on (time, source, event_id) to check for existence
    let source   = row.source.clone();
    let time     = row.time.clone();
    let event_id = row.event_id;

    let mut result = db
        .query("SELECT id FROM event WHERE time = $time AND event_id = $event_id AND source = $source LIMIT 1")
        .bind(("time",     time))
        .bind(("event_id", event_id as i64))
        .bind(("source",   source))
        .await?;

    let existing: Option<surrealdb::sql::Value> = result.take(0)?;

    if existing.is_some() {
        return Ok(false);
    }

    let created: Option<EventRow> = db
        .create("event")
        .content(row)
        .await
        .context("Failed to insert parsed event")?;

    Ok(created.is_some())
}

fn parse_event_xml(xml: &str, channel: &str) -> AppResult<EventRow> {
    let mut reader = Reader::from_str(xml);
    reader.config_mut().trim_text(true);

    let mut time_str = String::new();
    let mut level = String::from("0");
    let mut provider = String::from("Unknown");
    let mut event_id = 0;
    let mut message = String::new();
    let mut event_data = Vec::new();

    let mut in_message = false;
    let mut in_data = false;
    let mut current_data_name = String::new();

    loop {
        match reader.read_event() {
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) => match e.name().as_ref() {
                b"TimeCreated" => {
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"SystemTime" {
                            time_str = String::from_utf8_lossy(&attr.value).into_owned();
                        }
                    }
                }
                b"Provider" => {
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"Name" {
                            provider = String::from_utf8_lossy(&attr.value).into_owned();
                        }
                    }
                }
                b"Level" => {
                    level = reader.read_text(e.name())
                        .map_err(|e| anyhow::anyhow!("XML text read error: {}", e))?.into_owned();
                }
                b"EventID" => {
                    let id_str = reader.read_text(e.name())
                        .map_err(|e| anyhow::anyhow!("XML text read error: {}", e))?;
                    event_id = id_str.parse().unwrap_or(0);
                }
                b"Message" => {
                    in_message = true;
                }
                b"Data" => {
                    in_data = true;
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"Name" {
                            current_data_name = String::from_utf8_lossy(&attr.value).into_owned();
                        }
                    }
                }
                _ => (),
            },
            Ok(Event::Text(e)) => {
                let text = String::from_utf8_lossy(e.as_ref()).into_owned();
                if in_message {
                    message = text;
                } else if in_data {
                    if current_data_name.is_empty() {
                        event_data.push(text);
                    } else {
                        event_data.push(format!("{}: {}", current_data_name, text));
                    }
                }
            }
            Ok(Event::End(e)) => match e.name().as_ref() {
                b"Message" => in_message = false,
                b"Data" => {
                    in_data = false;
                    current_data_name.clear();
                }
                _ => (),
            },
            Ok(Event::Eof) => break,
            Err(e) => return Err(anyhow::anyhow!("XML parse error: {}", e).into()),
            _ => (),
        }
    }

    let time = DateTime::parse_from_rfc3339(&time_str)
        .map(|dt| dt.with_timezone(&Utc))
        .unwrap_or_else(|_| Utc::now());

    // Fallback: If message is empty, use event_data
    let final_message = if message.trim().is_empty() {
        if event_data.is_empty() {
            "No message or data".to_string()
        } else {
            event_data.join(" | ")
        }
    } else {
        message
    };

    // Map Windows numeric levels to human readable
    let human_level = match level.as_str() {
        "1" => "Critical",
        "2" => "Error",
        "3" => "Warning",
        "4" => "Information",
        "5" => "Verbose",
        _   => "Unknown",
    };

    Ok(EventRow {
        id: None,
        time: time.into(),
        level: human_level.to_string(),
        source: provider,
        event_id,
        message: final_message,
        channel: channel.to_string(),
        raw_xml: xml.to_string(),
    })
}

pub async fn query_events(
    state: &AppState,
    channel: Option<Channel>,
    level: Option<Level>,
    limit: usize,
    days_ago: Option<i64>,
) -> AppResult<Vec<EventRow>> {
    let db = state.db().await;

    let mut conditions = Vec::new();
    let mut bindings: Vec<(&'static str, String)> = Vec::new();
    
    if let Some(ch) = channel { 
        conditions.push("channel = $channel"); 
        bindings.push(("channel", ch.to_string()));
    }
    if let Some(lvl) = level { 
        conditions.push("level = $level"); 
        bindings.push(("level", lvl.to_string()));
    }
    if let Some(days) = days_ago {
        conditions.push("time > time::now() - <duration>(type::string($days) + 'd')");
        bindings.push(("days", days.to_string()));
    }

    let mut sql = String::from("SELECT * FROM event");
    if !conditions.is_empty() {
        sql.push_str(" WHERE ");
        sql.push_str(&conditions.join(" AND "));
    }
    sql.push_str(" ORDER BY time DESC LIMIT $limit");

    let mut q = db.query(&sql).bind(("limit", limit as i64));
    for (k, v) in bindings {
        q = q.bind((k, v));
    }

    let mut response = q
        .await
        .context("Database query failed")?;

    let events: Vec<EventRow> = response
        .take(0)
        .context("Failed to deserialize query results")?;

    Ok(events)
}
