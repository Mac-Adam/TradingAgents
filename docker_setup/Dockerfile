FROM python:3.11-slim

# Install SSH server, curl, git, nodejs, npm, and ollama CLI, then clear apt cache
RUN apt-get update && \
    apt-get install -y zstd openssh-server wget curl git nodejs npm && \
    curl -fsSL https://ollama.com/install.sh | sh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*


# Crucial: SSH daemon needs this specific directory to exist to run
RUN mkdir -p /run/sshd 

# Set a password for the root user
RUN echo 'root:password' | chpasswd

# Crucial: Allow root login with a password
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Install uv for fast python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app

COPY . /app/

WORKDIR /app/project_files/TradingAgents

RUN /root/.local/bin/uv pip install --system --no-cache-dir -r requirements.txt

EXPOSE 22

# 6. Start the SSH daemon
CMD ["/usr/sbin/sshd", "-D", "-e"]