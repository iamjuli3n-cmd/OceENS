#!/bin/bash

cd /home/mde-admin/OceENS

if [ ! -d venv ]; then 
	echo "venv not found. Installing"
	python3 -m venv venv
	source venv/bin/activate
	pip install -r requirements.txt
	deactivate
fi

if [ $(ps -aux | grep "app.py" | wc -l) -gt 1 ]; then
	echo "Website already launched"
else

	echo "Launching Website with screen"
	screen -d -m bash -c "source venv/bin/activate && python -u app.py 2> >(tee -a app.error) | tee -a app.log"
fi

if [ $(ps -aux | grep "summaries_generator_daemon.py" | wc -l) -gt 1 ]; then
	echo "Summaries generator already launched"
else

	echo "Launching Summaries generator with screen"
	screen -d -m bash -c "source venv/bin/activate && python -u summaries_generator_daemon.py 2> >(tee -a summaries.error) | tee -a summaries.log"
fi




