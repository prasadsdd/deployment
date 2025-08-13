# Use the official Python 3.11 image as the base image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
# This step is done early to leverage Docker's caching, so it only
# re-runs if requirements.txt changes.
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# This includes app.py, the static and templates folders, and the .env file.
COPY . .

# Expose port 5000, which is the default Flask port
EXPOSE 5000

# Set the FLASK_APP environment variable.
# This tells the 'flask' command where to find your application.
ENV FLASK_APP=app.py

# Define the command to run the application
# The host=0.0.0.0 is crucial to make the server accessible from outside the container.
CMD ["flask", "run", "--host=0.0.0.0"]
