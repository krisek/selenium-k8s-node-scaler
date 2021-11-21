FROM ubuntu:20.04 as needs-squashing
ENV LANG en_EN.UTF-8
ENV LANGUAGE en_EN
ENV LC_ALL C.UTF-8
ENV TZ=Europe/Berlin

ENV SUDO_FORCE_REMOVE yes

RUN apt-get update && apt-get upgrade -q -y && apt install -y python3-pip apt-transport-https curl fish git python3-virtualenv tree
RUN mkdir /usr/lib/selenium-k8s-node-scaler
COPY requirements.txt selenium-k8s-node-scaler.py pod.yaml.j2 /usr/lib/selenium-k8s-node-scaler/
RUN pip install -r /usr/lib/selenium-k8s-node-scaler/requirements.txt

RUN useradd -ms /usr/bin/fish scaler

USER scaler

