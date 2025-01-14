#!/bin/sh
echo "Contenuto della directory /data:"
ls -la /data
echo "\nInformazioni sul database:"
if [ -f /data/podcasts.db ]; then
    echo "Database esiste"
    sqlite3 /data/podcasts.db ".databases"
    sqlite3 /data/podcasts.db ".tables"
    sqlite3 /data/podcasts.db ".schema"
else
    echo "Database non esiste"
fi
