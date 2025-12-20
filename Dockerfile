ARG FFMPEG_VERSION=4.2.2
ARG CHROME_CHANNEL=stable

FROM ubuntu:20.04
ARG FFMPEG_VERSION
ENV CHROME_CHANNEL=${CHROME_CHANNEL}

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y software-properties-common && apt-get update

RUN ln -s -f /bin/true /usr/bin/chfn \
    && apt-get update && apt-get install -y \
        python3-pip \
        python3-dev \
        xvfb \
        fluxbox \
        ffmpeg \
        dbus-x11 \
        libasound2 \
        libasound2-plugins\
        libnss-wrapper \
        alsa-utils \
        alsa-oss \
        pulseaudio \
        pulseaudio-utils \
    && mkdir /home/lithium /var/run/pulse /run/user/lithium \
    && chown -R 1001:0 /home/lithium /run/user/lithium /var/run/pulse \
    && chmod -R g=u /home/lithium /run/user/lithium /var/run/pulse

RUN ln -s /usr/bin/python3 /usr/local/bin/python \
    && pip3 install --upgrade pip

COPY py_requirements.txt ./

RUN pip install --no-cache-dir -r py_requirements.txt



RUN apt-get update && \
    apt-get install -y wget curl unzip --no-install-recommends && \
    # Determine desired Chrome channel (Stable, Beta, Dev, Canary)
    case "$CHROME_CHANNEL" in \
      stable|Stable) CHAN_KEY=Stable;; \
      beta|Beta) CHAN_KEY=Beta;; \
      dev|Dev) CHAN_KEY=Dev;; \
      canary|Canary) CHAN_KEY=Canary;; \
      *) CHAN_KEY=Stable;; \
    esac && \
    # Try primary CfT JSON endpoint; fallback to text endpoint if unavailable
    if curl -fsSL https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json -o /tmp/cft.json; then \
      python3 -c "import json; chan='${CHAN_KEY}'; d=json.load(open('/tmp/cft.json')); s=d['channels'][chan]; print([u['url'] for u in s['downloads']['chrome'] if u['platform']=='linux64'][0], [u['url'] for u in s['downloads']['chromedriver'] if u['platform']=='linux64'][0])" | tee /tmp/cft_urls.txt; \
      CHROME_URL=$(awk '{print $1}' /tmp/cft_urls.txt); \
      DRIVER_URL=$(awk '{print $2}' /tmp/cft_urls.txt); \
    else \
      CHAN_API=$(printf "%s" "$CHAN_KEY" | tr '[:lower:]' '[:upper:]'); \
      CHROME_VER=$(curl -fsSL https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_${CHAN_API}); \
      CHROME_URL="https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VER}/linux64/chrome-linux64.zip"; \
      DRIVER_URL="https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VER}/linux64/chromedriver-linux64.zip"; \
    fi && \
    wget -q -O /tmp/chrome-linux64.zip "$CHROME_URL" && \
    wget -q -O /tmp/chromedriver-linux64.zip "$DRIVER_URL" && \
    unzip -o /tmp/chrome-linux64.zip -d /opt && \
    unzip -o /tmp/chromedriver-linux64.zip -d /usr/src/app && \
    ln -sf /opt/chrome-linux64/chrome /usr/bin/google-chrome && \
    ln -sf /usr/src/app/chromedriver-linux64/chromedriver /usr/src/app/chromedriver && \
    chmod +x /usr/src/app/chromedriver && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      libnss3 libnspr4 libxss1 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
      libdrm2 libgbm1 libgtk-3-0 libxdamage1 libxext6 libxfixes3 \
      libxcomposite1 libxrandr2 libxrender1 libxcb1 libx11-6 \
      libpangocairo-1.0-0 libpango-1.0-0 libcurl4 ca-certificates fonts-liberation xdg-utils \
      firefox libdbus-glib-1-2 && \
    # Install geckodriver (latest), with fallback to a pinned version
    if curl -fsSL https://api.github.com/repos/mozilla/geckodriver/releases/latest -o /tmp/gecko.json; then \
      GECKO_URL=$(python3 -c "import json,sys; d=json.load(open('/tmp/gecko.json')); urls=[a.get('browser_download_url','') for a in d.get('assets',[]) if 'linux64' in a.get('browser_download_url','') and a.get('browser_download_url','').endswith('.tar.gz')]; print(urls[0] if urls else sys.exit(1))"); \
    else \
      GECKO_URL="https://github.com/mozilla/geckodriver/releases/download/v0.34.0/geckodriver-v0.34.0-linux64.tar.gz"; \
    fi && \
    wget -q -O /tmp/geckodriver.tgz "$GECKO_URL" && \
    tar -xzf /tmp/geckodriver.tgz -C /usr/local/bin && \
    chmod +x /usr/local/bin/geckodriver && \
    google-chrome --version && /usr/src/app/chromedriver --version && \
    firefox --version && geckodriver --version && \
    pwd && ls

ENV BBB_RESOLUTION 1920x1080
ENV BBB_AS_MODERATOR false
ENV BBB_USER_NAME Live
ENV BBB_CHAT_NAME Chat
ENV BBB_SHOW_CHAT false
ENV BBB_ENABLE_CHAT false
ENV BBB_REDIS_HOST redis
ENV BBB_REDIS_CHANNEL chat
RUN DEBIAN_FRONTEND="noninteractive" apt-get -y install tzdata
ENV TZ Europe/Vienna
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY stream.py ./
COPY chat.py ./
COPY startStream.sh ./
COPY docker-entrypoint.sh ./
COPY nsswrapper.sh ./

# Ensure logs directory exists and is writable by the app user
RUN mkdir -p /usr/src/app/logs && \
    chown -R 1001:0 /usr/src/app/logs && \
    chmod -R g=u /usr/src/app/logs

ENTRYPOINT ["sh","docker-entrypoint.sh"]

CMD ["sh","startStream.sh" ]
USER 1001
