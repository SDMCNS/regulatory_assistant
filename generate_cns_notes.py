import requests
import random
import time
from datetime import datetime, timedelta

API_URL = "http://localhost:8000/regulations/notes"

topics = [
    "VHF Data Exchange System (VDES) Upgrade",
    "Space-Based ADS-B Integration",
    "Global Navigation Satellite System (GNSS) Modernization",
    "System Wide Information Management (SWIM) Deployment",
    "Aeronautical Telecommunication Network (ATN) Transition",
    "Controller-Pilot Data Link Communications (CPDLC) Extension",
    "Surface Movement Radar (SMR) Upgrades",
    "Performance-Based Navigation (PBN) Implementation",
    "Wide Area Augmentation System (WAAS) Enhancements",
    "Mode S Secondary Surveillance Radar Maintenance"
]

meeting_types = [
    "Meeting Minutes",
    "Internal Working Paper",
    "Project Status Report",
    "Risk Assessment Log",
    "Technical Briefing",
    "Stakeholder Update",
    "System Requirements Review",
    "Incident Report"
]

authors = ["Alice Smith (Project Lead)", "Bob Jones (Systems Engineer)", "Charlie Davis (Safety Inspector)", "Diana Prince (Comms Specialist)", "Evan Wright (Nav Coordinator)"]

tags_pool = ["CNS", "communication", "navigation", "surveillance", "ATM", "safety", "compliance", "upgrade", "maintenance", "integration", "satellite", "radar"]

def random_date(start_days_ago=365):
    now = datetime.now()
    delta = timedelta(days=random.randint(0, start_days_ago))
    return (now - delta).strftime("%Y-%m-%d")

def generate_notes(num_notes=50):
    success_count = 0
    for i in range(num_notes):
        topic = random.choice(topics)
        m_type = random.choice(meeting_types)
        author = random.choice(authors)
        date = random_date()
        tags = random.sample(tags_pool, k=random.randint(2, 5))
        
        title = f"[{m_type}] {topic} - {date}"
        project = topic
        note_type = "project_note" if m_type in ["Project Status Report", "Technical Briefing"] else ("meeting_minutes" if m_type == "Meeting Minutes" else "general_note")
        
        description = f"Overview of the latest developments regarding {topic}. Discussed technical challenges, compliance with EASA regulations, and upcoming milestones."
        
        sections = []
        num_sections = random.randint(2, 4)
        for s in range(num_sections):
            sections.append({
                "section_number": str(s+1),
                "heading": f"Section {s+1}: {random.choice(['Updates', 'Challenges', 'Action Items', 'Compliance Checks'])}",
                "content": f"In this section, we discussed the integration of {topic} into the broader ATM network. It is crucial to maintain backwards compatibility while upgrading to the new standard. Action item: {author} to verify safety margins.",
                "tags": random.sample(tags, k=min(2, len(tags)))
            })
            
        payload = {
            "title": title,
            "note_type": note_type,
            "date": date,
            "author": author,
            "project": project,
            "tags": tags,
            "description": description,
            "sections": sections,
            "auto_embed": True  # Instructs API to embed immediately
        }
        
        try:
            print(f"Sending note {i+1}/{num_notes}: {title}")
            res = requests.post(API_URL, json=payload, timeout=30)
            if res.status_code == 200:
                success_count += 1
                print(f"  Success: {res.json().get('document_id')}")
            else:
                print(f"  Failed: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"  Error: {e}")
            
        time.sleep(1) # Small delay to not overwhelm the embedding server
        
    print(f"\nFinished. Successfully created {success_count}/{num_notes} notes.")

if __name__ == '__main__':
    generate_notes(50)
