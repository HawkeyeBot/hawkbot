FROM python:3.11

EXPOSE 6969

WORKDIR /src

RUN pip install Cython==3.0.10 numpy==1.23.5 # install Cython & numpy first to avoid errors of pip
COPY ./requirements.txt /src/requirements.txt
RUN pip install --upgrade -r /src/requirements.txt

COPY LICENSE trade.py logging.yaml /src/
COPY ./hawkbot /src/hawkbot
COPY ./hawkbot_rt/__init__.py /src/hawkbot_rt/
COPY ./hawkbot_rt/py311 /src/hawkbot_rt/py311