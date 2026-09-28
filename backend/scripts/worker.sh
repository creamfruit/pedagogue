#!/bin/sh
set -e
exec arq app.workers.queue.WorkerSettings
