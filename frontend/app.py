import gradio as gr
import asyncio
import json
import os
from client import RViewerClient, format_events_to_df
import pandas as pd

# Initialize the backend client
api = RViewerClient()
SETTINGS_PATH = "settings.json"

def load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r") as f:
                return json.load(f)
        except:
            pass
    return {
        "channel": "All",
        "level": "All",
        "limit": 50,
        "days_ago": 7
    }

def save_settings(channel, level, limit, days_ago):
    settings = {
        "channel": channel,
        "level": level,
        "limit": limit,
        "days_ago": days_ago
    }
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f)
    gr.Info("Filters saved successfully!")
    return gr.update()

async def fetch_logs(channel, level, limit, days_ago):
    """Callback for the 'Refresh' and 'Query' buttons."""
    api_channel = None if channel == "All" else channel
    api_level = None if level == "All" else level
    
    events = await api.get_events(
        channel=api_channel, 
        level=api_level, 
        limit=limit,
        days_ago=days_ago
    )
    df = format_events_to_df(events)
    # Return both the DataFrame and the original events list for the detail view
    return df, events

def get_row_details(evt: gr.SelectData, current_events):
    """Triggered when a row is selected in the DataFrame."""
    if not current_events or evt.index[0] >= len(current_events):
        return "No data available", ""
    
    event = current_events[evt.index[0]]
    message = event.get("message", "N/A")
    raw_xml = event.get("raw_xml", "N/A")
    
    return message, raw_xml

async def trigger_ingest(channel, limit):
    """Callback for the 'Ingest' button."""
    gr.Info(f"Starting ingestion for {channel}...")
    result = await api.ingest_logs(channel=channel, limit=limit)
    
    if result.get("success"):
        count = result.get("data", 0)
        gr.Info(f"Successfully ingested {count} events!")
        return await fetch_logs("All", "All", 50, 7)
    else:
        gr.Error(f"Ingestion failed: {result.get('error')}")
        return gr.update(), []

async def check_status():
    """Timer callback to check backend health."""
    health = await api.get_health()
    if health.get("success"):
        return "🟢 Backend Online"
    else:
        return "🔴 Backend Offline (Make sure Rust server is running on port 8080)"

# Theme for a premium look
theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="slate",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
).set(
    button_primary_background_fill="*primary_600",
    button_primary_background_fill_hover="*primary_500",
)

initial_settings = load_settings()

with gr.Blocks(theme=theme, title="R_viewer | Windows Event Explorer") as demo:
    # State to keep track of full event data independently from the displayed table
    current_events_state = gr.State([])

    gr.Markdown(
        """
        # 🛡️ R_viewer
        ### Modern Windows Event Log Explorer
        """
    )
    
    with gr.Row():
        status_md = gr.Markdown("Checking backend status...", label="Status")
        refresh_status_btn = gr.Button("🔄 Check Status", variant="secondary", size="sm")

    with gr.Tabs():
        # --- TAB 1: EXPLORER ---
        with gr.Tab("🔍 Event Explorer"):
            with gr.Row():
                with gr.Column(scale=1):
                    channel_drop = gr.Dropdown(
                        choices=["All", "System", "Application", "Security"], 
                        value=initial_settings["channel"], 
                        label="Channel"
                    )
                    level_drop = gr.Dropdown(
                        choices=["All", "Critical", "Error", "Warning", "Information", "Verbose"], 
                        value=initial_settings["level"], 
                        label="Level"
                    )
                    days_slider = gr.Slider(
                        minimum=1, maximum=90, step=1, 
                        value=initial_settings["days_ago"], 
                        label="Time Filter (Last N Days)"
                    )
                    limit_slider = gr.Slider(
                        minimum=10, maximum=1000, step=10, 
                        value=initial_settings["limit"], 
                        label="Limit"
                    )
                    with gr.Row():
                        query_btn = gr.Button("Query Logs", variant="primary")
                        save_btn = gr.Button("💾 Save Filters", variant="secondary")
                
                with gr.Column(scale=4):
                    log_output = gr.DataFrame(
                        headers=["Time", "Level", "Source", "ID", "Message", "Channel"],
                        interactive=False,
                        label="Event Logs (Click a row to see details)",
                        wrap=False, # Disable wrap for compact view
                        column_widths=["120px", "80px", "150px", "60px", "auto", "100px"]
                    )
            
            # --- DETAILS SECTION ---
            with gr.Accordion("📋 Event Details", open=False) as details_accordion:
                with gr.Row():
                    with gr.Column(scale=1):
                        full_message = gr.Textbox(label="Full Message", lines=10, max_lines=20, interactive=False)
                    with gr.Column(scale=1):
                        raw_xml_view = gr.Textbox(label="Raw XML (Debugging)", lines=10, max_lines=20, interactive=False)

        # --- TAB 2: INGESTION ---
        with gr.Tab("⚡ Ingest Logs"):
            gr.Markdown("Directly pull new logs from Windows Event Vitals into SurrealDB.")
            with gr.Row():
                ingest_channel = gr.Dropdown(
                    choices=["System", "Application", "Security"], 
                    value="System", 
                    label="Source Channel"
                )
                ingest_limit = gr.Number(value=100, label="Ingest Limit")
                ingest_btn = gr.Button("🚀 Start Ingestion", variant="primary")

    # Interactivity
    query_btn.click(
        fn=fetch_logs, 
        inputs=[channel_drop, level_drop, limit_slider, days_slider], 
        outputs=[log_output, current_events_state]
    )
    
    # Row Selection: Show details and open the accordion
    log_output.select(
        fn=get_row_details,
        inputs=[current_events_state],
        outputs=[full_message, raw_xml_view]
    ).then(
        fn=lambda: gr.update(open=True),
        inputs=None,
        outputs=details_accordion
    )
    
    save_btn.click(
        fn=save_settings,
        inputs=[channel_drop, level_drop, limit_slider, days_slider],
        outputs=[]
    )
    
    ingest_btn.click(
        fn=trigger_ingest,
        inputs=[ingest_channel, ingest_limit],
        outputs=[log_output, current_events_state]
    )

    refresh_status_btn.click(fn=check_status, outputs=status_md)

    # Initial load behavior
    demo.load(fn=check_status, outputs=status_md)
    demo.load(
        fn=fetch_logs, 
        inputs=[channel_drop, level_drop, limit_slider, days_slider], 
        outputs=[log_output, current_events_state]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
