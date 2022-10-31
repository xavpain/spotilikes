#!/bin/python3.8
from importlib.metadata import requires
import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask_session import Session
from flask import Flask, render_template, session, request, redirect, flash
from flask_pymongo import PyMongo
from pymongo.collection import Collection, ReturnDocument
from pymongo import MongoClient


load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(64)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './.flask_session/'
# app.config['MONGO_URI'] = os.getenv("MONGO_URI")
mongocli = MongoClient(os.getenv("MONGO_URI"))
Session(app)
likes_db: Collection = mongocli.appdb.get_collection('likes')
# db.get_collection

scope = "user-read-currently-playing user-read-playback-position user-top-read user-read-recently-played user-library-modify user-library-read playlist-read-private playlist-read-collaborative"
default_pic = "https://i.scdn.co/image/ab6761610000e5eb1020c22e0ce742eca7166e65"

def check_session():
    cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
    auth_manager = spotipy.oauth2.SpotifyOAuth(scope=scope, cache_handler=cache_handler, redirect_uri="http://spotilikes.herokuapp.com")
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return None
    return spotipy.Spotify(auth_manager=auth_manager)

def trim_user(user):
    return {
        "username": user["display_name"],
        "pic": default_pic if user['images'] == [] else user['images'][0]['url'],
        "id": user['id']
    }

@app.route('/')
def index():
    cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
    auth_manager=SpotifyOAuth(scope=scope, redirect_uri="http://spotilikes.herokuapp.com", cache_handler=cache_handler, show_dialog=True)
    
    if request.args.get("code"):
        auth_manager.get_access_token(request.args.get("code"))
        return redirect('/')

    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        auth_url = auth_manager.get_authorize_url()
        return render_template('base.html', is_auth=False, auth_url=auth_manager.get_authorize_url())

    spotify = spotipy.Spotify(auth_manager=auth_manager)
    return redirect('/home')

@app.route('/sign_out')
def sign_out():
    session.pop("token_info", None)
    return redirect('/')

@app.route('/playing')
def playing():
    sp = check_session()
    if sp is None:
        return redirect('/')
    track = sp.current_user_playing_track()
    if not track is None:
        return track
    return "No track currently playing."

@app.route('/home')
def show_users():
    sp = check_session()
    if sp is None:
        flash("Unauthorized", category='error')
        return redirect('/')
    users = list(likes_db.find())

    # ex = {"userid": "zz",
    # "username": "placeholdername",
    # "userpic": "https://i.scdn.co/image/ab6775700000ee851e3a212349c50c082f1845d4",
    # "likes":[]}
    # users += ([ex] * 30)

    client = trim_user(sp.me())
    is_empty = any(i["userid"] == client["id"] for i in users)
    return render_template('likes.html', is_auth=True, client=client, users=users, is_empty=is_empty)

@app.route('/likes')
def update_likes():
    sp = check_session()
    if sp is None:
        flash("Unauthorized", category='error')
        return redirect('/')
    user = sp.current_user()
    data = {"userid": user['id'], "username": user['display_name'], "userpic": default_pic if user['images'] == [] else user['images'][0]['url'],'likes': []}
    songs = sp.current_user_saved_tracks(limit=50)
    while songs:
        for i in songs['items']:
            data['likes'].append({
                "trackid": i['track']['id'],
                })
        if songs['next']:
            songs = sp.next(songs)
        else:
            songs = None
    likes_db.replace_one(upsert=True, filter={"userid": user['id']}, replacement=data)
    flash("Sucessfully updated your liked songs!", category='success')
    return redirect('/home')
if __name__ == '__main__':
    app.run(threaded=True, port=3000)

##IF I EVER NEED TO GET EXTRA TINGS
def trim_track(track):
    return {"name": track["name"], "link": track['external_urls']['spotify']}
    
@app.route('/mutual', methods=['POST'])
def get_mutual():
    sp = check_session()
    if sp is None:
        flash("Unauthorized", category='error')
        return redirect('/')
    target_id = request.form.get('mutual')
    my_id = sp.me()['id']
    if target_id == my_id:
        flash("bro u can't compare yourself with yourself xdd", category='error')
        return redirect('/home')
    target = likes_db.find_one({"userid":target_id})
    me = likes_db.find_one({"userid":my_id})
    if not target:
        flash("smth wild happened idk LOL", category='error')
        return redirect('/home')
    commonids = list(set(i["trackid"] for i in me["likes"]).intersection(set(i["trackid"] for i in target["likes"])))
    # tracks = list((trim_track(sp.track(i)) for i in commonids))
    return render_template('mutual.html', is_auth=True, client=trim_user(sp.me()), songs=commonids)

