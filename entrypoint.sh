#!/bin/sh

while true; do
    echo "Avvio Uvicorn..."

    uvicorn main:app --proxy-headers --port 5000 --host 0.0.0.0 --forwarded-allow-ips "*" --reload
    echo "Uvicorn terminato con codice $?. Riavvio tra 5 secondi..."
    sleep 5
done
