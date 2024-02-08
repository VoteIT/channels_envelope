.DEFAULT_GOAL := install

install:
	pip install -r requirements.txt

coverage:
	coverage run ./manage.py test envelope --keepdb && coverage report

migrations:
	./manage.py makemigrations

migrate:
	./manage.py migrate

rqworker:
	./manage.py rqworker default

run:
	./manage.py runserver

test:
	./manage.py test envelope --keepdb
