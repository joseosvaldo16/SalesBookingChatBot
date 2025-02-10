# Use an official Python ruslimntime as a parent image
FROM python:3.11-slim-bullseye

# Set the working directory in the container
WORKDIR /BotApp

# Set environment variables
ENV ACCEPT_EULA=Y

RUN apt-get update && apt-get install -y --no-install-recommends \
        unixodbc \
        unixodbc-dev \
        g++ \
        gnupg2 \
        curl \
        ca-certificates \
    && curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft-archive-keyring.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-archive-keyring.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \ 
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install -U -r requirements.txt
    
# Copy static files to the wwwroot directory
COPY Vector_Stores/ Vector_Stores/
COPY src/ src/
COPY app.py .
COPY config.py .
COPY ./webfiles/index.html /home/site/wwwroot/index.html
COPY ./webfiles/style-v1.css /home/site/wwwroot/style-v1.css
COPY ./webfiles/midtronics-logo.png /home/site/wwwroot/midtronics-logo.png
# Set the environment variable for the port

EXPOSE 443
EXPOSE 80
EXPOSE 3978

# Run app.py when the container launches
CMD ["python", "./app.py"]
