from . import app
import os
import json
import pymongo
from flask import jsonify, request, make_response, abort, url_for
from pymongo import MongoClient
from bson import json_util
from pymongo.errors import OperationFailure
from bson.objectid import ObjectId
import sys
from http import HTTPStatus

SITE_ROOT = os.path.realpath(os.path.dirname(__file__))
json_url = os.path.join(SITE_ROOT, "data", "songs.json")
songs_list: list = json.load(open(json_url))

# MongoDB configuration
mongodb_service = os.environ.get('MONGODB_SERVICE')
mongodb_username = os.environ.get('MONGODB_USERNAME')
mongodb_password = os.environ.get('MONGODB_PASSWORD')
mongodb_port = os.environ.get('MONGODB_PORT')

print(f'The value of MONGODB_SERVICE is: {mongodb_service}')

if mongodb_service is None:
    app.logger.error('Missing MongoDB server in the MONGODB_SERVICE variable')
    sys.exit(1)

if mongodb_username and mongodb_password:
    url = f"mongodb://{mongodb_username}:{mongodb_password}@{mongodb_service}"
else:
    url = f"mongodb://{mongodb_service}"

print(f"connecting to url: {url}")

try:
    client = MongoClient(url)
except OperationFailure as e:
    app.logger.error(f"Authentication error: {str(e)}")
    sys.exit(1)

db = client.songs
db.songs.drop()
db.songs.insert_many(songs_list)

def parse_json(data):
    return json.loads(json_util.dumps(data))

######################################################################
# ROUTES
######################################################################

@app.route("/", methods=["GET"])
def index():
    """Root endpoint that returns a welcome message"""
    return jsonify(
        name="Songs REST API Service",
        version="1.0",
        docs=url_for('index', _external=True) + "apidocs/index.html"
    )

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify(status="OK"), HTTPStatus.OK

@app.route("/count", methods=["GET"])
def count_songs():
    """Return the total count of songs in the database"""
    try:
        count = db.songs.count_documents({})
        return jsonify({"count": count}), HTTPStatus.OK
    except Exception as e:
        app.logger.error(f"Error counting songs: {str(e)}")
        return jsonify({"error": "Internal server error"}), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route("/song", methods=["GET", "POST"])
def handle_songs():
    """Handle GET and POST requests for songs"""
    if request.method == "POST":
        return create_song()
    else:
        return get_all_songs()

def get_all_songs():
    """Return all songs in the database"""
    try:
        songs = list(db.songs.find({}))
        return jsonify({"songs": parse_json(songs)}), HTTPStatus.OK
    except Exception as e:
        app.logger.error(f"Error fetching songs: {str(e)}")
        return jsonify({"error": "Internal server error"}), HTTPStatus.INTERNAL_SERVER_ERROR

def create_song():
    """Create a new song"""
    try:
        song = request.get_json()
        if not song:
            return jsonify({"error": "No input data provided"}), HTTPStatus.BAD_REQUEST

        if 'id' in song:
            existing_song = db.songs.find_one({"id": song['id']})
            if existing_song:
                return jsonify({"Message": f"song with id {song['id']} already present"}), HTTPStatus.FOUND

        result = db.songs.insert_one(song)
        new_song = db.songs.find_one({"_id": result.inserted_id})
        return jsonify(parse_json(new_song)), HTTPStatus.CREATED
    except Exception as e:
        app.logger.error(f"Error creating song: {str(e)}")
        return jsonify({"error": "Failed to create song"}), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route("/song/<int:id>", methods=["GET", "PUT", "DELETE"])
def handle_song(id):
    """Handle GET, PUT, and DELETE requests for a specific song"""
    if request.method == "PUT":
        try:
            song_data = request.get_json()
            if not song_data:
                return jsonify({"error": "No input data provided"}), HTTPStatus.BAD_REQUEST

            updated_song = db.songs.find_one_and_update(
                {"id": id},
                {"$set": song_data},
                return_document=pymongo.ReturnDocument.AFTER
            )
            
            if not updated_song:
                return jsonify({"message": "song not found"}), HTTPStatus.NOT_FOUND
                
            return jsonify(parse_json(updated_song)), HTTPStatus.CREATED
            
        except Exception as e:
            app.logger.error(f"Error updating song: {str(e)}")
            return jsonify({"error": "Failed to update song"}), HTTPStatus.INTERNAL_SERVER_ERROR
    elif request.method == "DELETE":
        try:
            result = db.songs.delete_one({"id": id})
            if result.deleted_count == 0:
                return jsonify({"message": "song not found"}), HTTPStatus.NOT_FOUND
            return "", HTTPStatus.NO_CONTENT
        except Exception as e:
            app.logger.error(f"Error deleting song: {str(e)}")
            return jsonify({"error": "Failed to delete song"}), HTTPStatus.INTERNAL_SERVER_ERROR
    else:
        song = db.songs.find_one({"id": id})
        if song:
            return jsonify(parse_json(song)), HTTPStatus.OK
        return jsonify({"message": "song not found"}), HTTPStatus.NOT_FOUND

@app.route("/songs", methods=["GET"])
def get_songs():
    """Alternative endpoint to return all songs"""
    try:
        songs = list(db.songs.find({}))
        return jsonify(parse_json(songs)), HTTPStatus.OK
    except Exception as e:
        app.logger.error(f"Error fetching songs: {str(e)}")
        return jsonify({"error": "Internal server error"}), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route("/songs/<id>", methods=["GET"])
def get_song(id):
    """Return a single song by ID (numeric or ObjectId)"""
    try:
        if id.isdigit():
            song = db.songs.find_one({"id": int(id)})
        else:
            try:
                song = db.songs.find_one({"_id": ObjectId(id)})
            except:
                song = None
        
        if song:
            return jsonify(parse_json(song)), HTTPStatus.OK
        return jsonify({"message": "Song not found"}), HTTPStatus.NOT_FOUND
    except Exception as e:
        app.logger.error(f"Invalid song ID: {id}, error: {str(e)}")
        return jsonify({"error": "Invalid song ID"}), HTTPStatus.BAD_REQUEST

@app.route("/songs", methods=["POST"])
def create_song_legacy():
    """Legacy endpoint for creating songs"""
    return create_song()

@app.route("/songs/<id>", methods=["PUT"])
def update_song_legacy(id):
    """Legacy endpoint for updating songs"""
    try:
        song_data = request.get_json()
        if not song_data:
            return jsonify({"error": "No input data provided"}), HTTPStatus.BAD_REQUEST

        if id.isdigit():
            updated_song = db.songs.find_one_and_update(
                {"id": int(id)},
                {"$set": song_data},
                return_document=pymongo.ReturnDocument.AFTER
            )
        else:
            try:
                updated_song = db.songs.find_one_and_update(
                    {"_id": ObjectId(id)},
                    {"$set": song_data},
                    return_document=pymongo.ReturnDocument.AFTER
                )
            except:
                return jsonify({"error": "Invalid song ID format"}), HTTPStatus.BAD_REQUEST
        
        if not updated_song:
            return jsonify({"message": "song not found"}), HTTPStatus.NOT_FOUND
            
        return jsonify(parse_json(updated_song)), HTTPStatus.CREATED
    except Exception as e:
        app.logger.error(f"Error updating song: {str(e)}")
        return jsonify({"error": "Failed to update song"}), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route("/songs/<id>", methods=["DELETE"])
def delete_song_legacy(id):
    """Legacy endpoint for deleting songs"""
    try:
        if id.isdigit():
            result = db.songs.delete_one({"id": int(id)})
        else:
            try:
                result = db.songs.delete_one({"_id": ObjectId(id)})
            except:
                result = None
        
        if not result or result.deleted_count == 0:
            return jsonify({"message": "Song not found"}), HTTPStatus.NOT_FOUND
        return "", HTTPStatus.NO_CONTENT
    except Exception as e:
        app.logger.error(f"Error deleting song: {str(e)}")
        return jsonify({"error": "Failed to delete song"}), HTTPStatus.INTERNAL_SERVER_ERROR
