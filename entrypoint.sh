#!/bin/bash

# Start the app server in the background
python app_server.py &

# Run the main script (this will keep the container running)
python main.py
