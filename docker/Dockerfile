FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Build PX4 and display Gazebo/Qt; no vision, CUDA, ROS or video stack.
RUN apt-get update && apt-get install -y --no-install-recommends \
    astyle bc build-essential ca-certificates ccache cmake cppcheck curl file \
    git gnupg lcov libssl-dev libxml2-dev libxml2-utils lsb-release ninja-build \
    pkg-config python3 python3-dev python3-pip python3-venv rsync unzip wget zip zsh \
    libegl1 libgl1 libglib2.0-0 libnss3 libx11-xcb1 libxcb-cursor0 libxcb-glx0 \
    libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcomposite1 libxdamage1 \
    libxkbcommon-x11-0 libxrandr2 libxtst6 libasound2 libdbus-1-3 libfontconfig1 \
    libqt5svg5 libopencv-dev libgstreamer-plugins-base1.0-dev \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q https://packages.osrfoundation.org/gazebo.gpg \
        -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo 'deb [signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable jammy main' \
        > /etc/apt/sources.list.d/gazebo-stable.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gz-harmonic libunwind-dev \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH} \
    QTWEBENGINE_DISABLE_SANDBOX=1 \
    QT_X11_NO_MITSHM=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN python3 -m venv /opt/venv && python -m pip install --upgrade pip wheel
COPY requirements.txt /tmp/app-requirements.txt
COPY docker/requirements-px4.txt /tmp/px4-requirements.txt
RUN python -m pip install -r /tmp/px4-requirements.txt \
    && python -m pip install -r /tmp/app-requirements.txt
RUN printf '%s\n' 'PROMPT="%F{cyan}[SW-UAV basic]%f %~ %# "' > /root/.zshrc
COPY . .
CMD ["sleep", "infinity"]
