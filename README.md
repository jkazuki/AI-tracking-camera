# Real-Time Behavior Monitoring & Zone Alert System

An advanced, real-time AI security monitoring system powered by **YOLOv8** and **ByteTrack**. Unlike traditional systems that require complex RTSP streams, this project utilizes **Windows Graphics Capture API** to grab frames directly from desktop applications (e.g., Imou Life, VMS software), making it highly flexible and easy to deploy.

![System Demo](demo.png)
*(Note: Replace demo.png with an actual screenshot or GIF of your system running)*

##  Key Features

*   **Direct Window Capture:** Grabs frames directly from camera software windows (like OBS), avoiding feedback loops and eliminating the need for RTSP links.
*   **Dynamic Zone Drawing (Zones A/B/C):** 
    *   Draw custom polygonal monitoring zones directly on the video feed.
    *   3-Tier Alert System (Level 0: Normal, Level 1: Yellow, Level 2: Flashing Red).
*   **Face Re-ID:** Uses facial recognition to automatically reconnect tracking IDs if a person is temporarily obscured or if the frame rate drops.
*   **Static Object Filter:** Automatically ignores stationary objects that the AI mistakenly identifies as people over a set period.
*   **Dual Console Control:** 
    *   **CMD 1:** Dedicated alert terminal (requires `Y/N` confirmation for security breaches).
    *   **CMD 2:** Command terminal to assign zones, verify safe personnel, and set nicknames.

##  System Requirements

*   **OS:** Windows 10/11 (Required for Windows Capture API).
*   **Python:** Python 3.12 recommended.
*   **Hardware:** A dedicated GPU (NVIDIA RTX 3060 12GB or higher recommended) is highly advised to maintain 30-60 FPS for real-time processing.
