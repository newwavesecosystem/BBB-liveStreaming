# Use newer Ubuntu base (Jammy = 22.04 LTS)
FROM ubuntu:jammy

ARG FFMPEG_VERSION=4.2.2
WORKDIR /usr/src/app

# Avoid interactive tzdata prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    software-properties-common \
    python3-pip python3-dev \
    xvfb fluxbox ffmpeg \
    dbus-x11 libasound2 libasound2-plugins \
    libnss-wrapper alsa-utils alsa-oss \
    pulseaudio pulseaudio-utils \
    gnupg wget curl unzip --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Set up PulseAudio directories
RUN mkdir -p /home/lithium /var/run/pulse /run/user/lithium && \
    chown -R 1001:0 /home/lithium /run/user/lithium /var/run/pulse && \
    chmod -R g=u /home/lithium /run/user/lithium /var/run/pulse

# Symlink Python
RUN ln -s /usr/bin/python3 /usr/local/bin/python && \
    pip3 install --upgrade pip

# Copy requirements
COPY py_requirements.txt ./
RUN pip install --no-cache-dir -r py_requirements.txt

# -----------------------------
# ✅ Install Google Chrome + Chromedriver (safe modern approach)
# -----------------------------
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    CHROMEVER=$(google-chrome --version | grep -oE "[0-9.]+") && \
    CHROMEMAJOR=$(echo $CHROMEVER | cut -d. -f1) && \
    DRIVERVER=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROMEMAJOR}") && \
    wget -q --continue "https://chromedriver.storage.googleapis.com/${DRIVERVER}/chromedriver_linux64.zip" && \
    unzip chromedriver_linux64.zip -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -f chromedriver_linux64.zip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# -----------------------------
# Environment
# -----------------------------
ENV BBB_RESOLUTION=1920x1080 \
    BBB_AS_MODERATOR=false \
    BBB_USER_NAME=Live \
    BBB_CHAT_NAME=Chat \
    BBB_SHOW_CHAT=false \
    BBB_ENABLE_CHAT=false \
    BBB_REDIS_HOST=redis \
    BBB_REDIS_CHANNEL=chat \
    TZ=Europe/Vienna

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Copy project files
COPY stream.py ./ 
COPY chat.py ./ 
COPY startStream.sh ./ 
COPY docker-entrypoint.sh ./ 
COPY nsswrapper.sh ./

ENTRYPOINT ["sh", "docker-entrypoint.sh"]
CMD ["sh", "startStream.sh"]

USER 1001
