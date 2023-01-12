import base64
import json
import os
import requests
import sys

from flask import Flask, request
app = Flask(__name__)


with open("credentials", "r", encoding="utf-8") as file:
    contents = file.readlines()
    if len(contents) != 2:
        print("Error: Credentials file must only contain 2 credentials!", file=sys.stderr)
        raise ValueError

    CLIENT_ID = contents[0].strip()
    CLIENT_SECRET = contents[1].strip()

ENCODED_CLIENT = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode("ascii")).decode("ascii")
DENYLIST = {
    "they're": "they are",
    "year's": "years",
}

def get_page(auth_token, subphrase, track_limit, offset):
    subphrase = subphrase.replace(" ", "%20")
    url = f"https://api.spotify.com/v1/search?q={subphrase}&type=track&limit={track_limit}&offset={offset}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    }
    response = requests.get(url=url, headers=headers).json()
    if "tracks" in response and "items" in response["tracks"]:
        return response["tracks"]["items"]
    else:
        return {}

def search_songs(auth_token, subphrase, track_limit):
    offset = 0
    page = 0
    while True:
        page_of_results = get_page(auth_token, subphrase, track_limit, offset)
        if len(page_of_results) == 0:
            print(f"\nCannot find: '{subphrase}'")
            return None
        else:
            page += 1
            for song in page_of_results:
                print(f"\rSearching page {page} for '{subphrase}'", end="")
                if song["name"].lower() == subphrase:
                    print(f'\nFOUND: {song["name"]} by {song["artists"][0]["name"]}')
                    return song
            offset += track_limit

def get_songs(auth_token, phrase, track_limit):
    subphrase = " ".join(phrase)
    songs_to_add = []
    cache = {}
    while len(phrase) > 0:
        for i in range(0 if len(phrase) <= 5 else len(phrase) - 4, len(phrase)):
            subphrase = " ".join(phrase[:-i] if i != 0 else phrase)
            if subphrase in DENYLIST:
                subphrase = blacklist[subphrase]
            if subphrase in cache:
                song = cache[subphrase]
                print(f"Using cached result for '{subphrase}'")
            else:
                song = search_songs(auth_token, subphrase, track_limit)
            if song != None:
                phrase = [] if i == 0 else phrase[-i:]
                break
        if song is not None:
            songs_to_add.append(song)
            cache[subphrase] = song
        else:
            break

    return songs_to_add

def create_playlist(auth_token, playlist_name, userid):
    print("Creating playlist...")
    url = f"https://api.spotify.com/v1/users/{userid}/playlists"
    data = json.dumps({
      "name": f"{playlist_name}",
      "description": f"{' '.join(phrase)}",
      "public": True,
    })
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    }

    response = requests.post(url=url, data=data, headers=headers).json()
    playlist_id = response["id"]
    playlist_url = response["external_urls"]["spotify"]

    return playlist_id, playlist_url

def add_to_playlist(auth_token, songs, playlist_id):
    print("Adding songs to playlist...")
    uris = ",".join([song["uri"]for song in songs])
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?uris={uris}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    }
    response = requests.post(url=url, headers=headers)

@app.route('/auth_callback')
def callback():
    url = "https://accounts.spotify.com/api/token"
    data = {
        "code": request.args["code"],
        "redirect_uri": "http://localhost:8509/auth_callback",
        "grant_type": "authorization_code",
    }
    headers = {
        "Authorization": f"Basic {ENCODED_CLIENT}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = requests.post(url=url, data=data, headers=headers).json()
    auth_token = response["access_token"]

    track_limit = 50 # max value
    userid = "s11vr90hshxqiw5juux7xiw0n"

    songs = get_songs(auth_token, phrase, track_limit)
    print("All songs found!")
    playlist_id, playlist_url = create_playlist(auth_token, playlist_name, userid)
    add_to_playlist(auth_token, songs, playlist_id)

    print(playlist_url)
    os.system(f"open {playlist_url}")
    return ""

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("""
Usage:
    python3 main.py "phrase" "playlist name"
""")
    else:
        phrase = sys.argv[1].lower()
        # Filter out non-alphabetical characters
        phrase = "".join([x for x in phrase if (ord(x) >= ord('a') and ord(x) <= ord('z')) or x == " " or x == "'"]).split()
        playlist_name = sys.argv[2]

        os.system("open https://accounts.spotify.com"
                  f"/authorize?response_type=code\\&client_id={CLIENT_ID}"
                  "\\&scope=playlist-modify-public"
                  "\\&redirect_uri=http://localhost:8509/auth_callback"
                  "\\&state=ramranch"
        )

        app.run(port=8509, host="0.0.0.0")
