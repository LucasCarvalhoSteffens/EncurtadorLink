import logging
import sqlite3
import hashlib
import redis
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from flask import Flask, request, g
from flask_restful import Resource, Api, abort
from werkzeug.local import LocalProxy

app = Flask(__name__)
api = Api(app)
tracer_provider = TracerProvider()

# Configuration for OTLP (OpenTelemetry Protocol) exporter
span_exporter = OTLPSpanExporter(endpoint="localhost:55680")
span_processor = BatchSpanProcessor(span_exporter)
tracer_provider.add_span_processor(span_processor)

# Configuration for the Trace Provider
trace.set_tracer_provider(tracer_provider)

# Configuration for the logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# Instrument HTTP requests
RequestsInstrumentor().instrument()

# SQLite database connection
def get_db():
    """Obtém a conexão do banco de dados atual da thread."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect('urls.db')
    return db

# Create a table for storing shortened URLs if it doesn't exist
with app.app_context():
    db = LocalProxy(get_db)
    cursor = db.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shortened_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_url TEXT NOT NULL,
            short_url TEXT NOT NULL
        )
    ''')
    db.commit()

# Redis connection
redis_client = redis.Redis(host='localhost', port=6379)

# Authorized API keys
AUTHORIZED_API_KEYS = {
    'Key1': 'user1',
    'Key2': 'user2',
    # Add more API keys and corresponding users as needed
}

class ShortenUrlResource(Resource):
    def get(self):
        # Check API key for authentication
        api_key = request.headers.get('X-API-Key')
        if api_key not in AUTHORIZED_API_KEYS:
            abort(401)  # Unauthorized

        url = request.args.get('url')

        # Check if the shortened URL exists in the cache
        cached_short_url = redis_client.get(url)
        if cached_short_url:
            return {'short_url': cached_short_url.decode()}

        with tracer_provider.get_tracer(__name__).start_as_current_span("shorten_url"):
            logger.info(f"Received URL: {url}")

            # Check if the shortened URL exists in the database
            short_url = fetch_short_url(url)
            if short_url:
                # Store the shortened URL in the cache
                redis_client.set(url, short_url)
                logger.info(f"Shortened URL (from database): {short_url}")
                return {'short_url': short_url}

            # Shorten the URL and store it in the database
            short_url = shorten_logic(url)
            store_url(url, short_url)

            # Store the shortened URL in the cache
            redis_client.set(url, short_url)

            logger.info(f"Shortened URL: {short_url}")
            return {'short_url': short_url}


def fetch_short_url(url):
    # Fetch the shortened URL from the database
    db = LocalProxy(get_db)  # Obtém a conexão do banco de dados atual da thread
    cursor = db.cursor()
    cursor.execute('SELECT short_url FROM shortened_urls WHERE original_url = ?', (url,))
    result = cursor.fetchone()
    if result:
        return result[0]
    return None


def shorten_logic(url):
    # Generate MD5 hash of the URL
    md5_hash = hashlib.md5(url.encode()).hexdigest()

    # Take the first 8 characters of the hash
    short_hash = md5_hash[:8]

    # Build the shortened URL using the short hash
    short_url = f"https://example.com/{short_hash}"

    return short_url


def store_url(original_url, short_url):
    # Store the original URL and the shortened URL in the database
    db = LocalProxy(get_db)  # Obtém a conexão do banco de dados atual da thread
    cursor = db.cursor()
    cursor.execute('INSERT INTO shortened_urls (original_url, short_url) VALUES (?, ?)', (original_url, short_url))
    db.commit()

@app.errorhandler(Exception)
def handle_error(e):
    logger.error('An internal server error occurred', exc_info=True)
    return {'error': 'Internal Server Error'}, 500


api.add_resource(ShortenUrlResource, '/shorten')

if __name__ == '__main__':
    app.run()
