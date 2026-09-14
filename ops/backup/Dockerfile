FROM postgres:17-alpine

RUN apk add --no-cache \
    age \
    bash \
    coreutils \
    curl \
    tzdata

WORKDIR /opt/bukvogon

COPY backup.sh restore.sh /opt/bukvogon/
COPY crontab /etc/crontabs/root

RUN chmod 0755 /opt/bukvogon/backup.sh /opt/bukvogon/restore.sh \
    && chmod 0600 /etc/crontabs/root \
    && mkdir -p /backups

ENV TZ=UTC

CMD ["crond", "-f", "-l", "2"]
