ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/ /app/
COPY addons/safety_component/run.sh /run.sh
RUN chmod +x /run.sh

WORKDIR /app

CMD [ "/run.sh" ]
