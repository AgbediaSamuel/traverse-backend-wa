# Traverse Backend

A high-performance backend service powering the Traverse platform—an intelligent travel planning and itinerary management solution. Built with **FastAPI** for speed and scalability, this service handles authentication, itinerary generation, calendar integrations, and place recommendations to deliver seamless travel experiences.

## Key Features

- **FastAPI Framework**: Modern, fast (high-performance) web framework with automatic OpenAPI documentation
- **Poetry Dependency Management**: Reliable and reproducible dependency resolution and virtual environment management
- **AI-Powered Itineraries**: Integrations with Anthropic, Google Generative AI, and OpenAI for intelligent travel planning
- **Authentication & Security**: Clerk integration with CSRF protection and secure middleware
- **MongoDB Storage**: Flexible document-based storage for itineraries, users, and travel data
- **RESTful API Design**: Clean, well-structured endpoints for auth, itineraries, calendars, and places

## Prerequisites

Before getting started, ensure you have the following installed:

- **Python 3.10+**
- **Poetry** (dependency manager)
  - macOS (Homebrew): `brew install poetry`
  - Official installer: `curl -sSL https://install.python-poetry.org | python3 -`

## Setup and Run

Follow these steps to get the development server running:

### 1. Install Dependencies

From the project root, install all required packages:

```bash
poetry install
```

### 2. Set Up the Virtual Environment

Activate the Poetry-managed virtual environment:

```bash
source $(poetry env info --path)/bin/activate
```

### 3. Configure Environment Variables

Create a `.env` file in the project root with the required configuration (refer to the team for necessary API keys and settings).

### 4. Start the Development Server

Run the server using the provided start script:

```bash
./scripts/start.sh
```

The API will be available at `http://localhost:8000` by default.

## Nginx Setup (Optional)

For local development with nginx reverse proxy (useful with ngrok):

1. Copy the nginx configuration:
   ```bash
   # macOS
   sudo cp infra/nginx-traverse.conf /opt/homebrew/etc/nginx/servers/traverse.conf
   
   # Linux
   sudo cp infra/nginx-traverse.conf /etc/nginx/sites-enabled/traverse.conf
   ```

2. Manage the nginx service:
   ```bash
   brew services start nginx    # Start
   brew services restart nginx  # Restart
   brew services stop nginx     # Stop
   ```

3. Access the app at `http://localhost:8080` through the nginx proxy.

## Contributing

We welcome contributions from team members! To contribute:

1. **Create a Branch**: Create a feature branch from `main` with a descriptive name (e.g., `feature/add-new-endpoint`).
2. **Make Changes**: Implement your changes following the existing code style and conventions.
3. **Write Tests**: Add or update tests in the `tests/` directory to cover your changes.
4. **Run Linting**: Ensure code quality by running:
   ```bash
   poetry run ruff check .
   poetry run black --check .
   ```
5. **Submit a Pull Request**: Open a PR with a clear description of your changes and request a review.

For questions or guidance, reach out to the team leads.

## License

**Proprietary Software**

This code is proprietary and confidential. All rights are reserved by the owner.

Unauthorized use, copying, modification, distribution, or reproduction of this software, in whole or in part, is strictly prohibited without explicit written permission from the owner.

For licensing inquiries, please contact the repository owner.

