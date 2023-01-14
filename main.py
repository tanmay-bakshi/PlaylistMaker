import base64
import json
import os
import requests
import sys

from pathlib import Path
from flask import Flask, request
from typing import Any, Dict, List, Optional, Tuple

Query = List[Dict[str, Any]]
app = Flask(__name__)

with (Path(__file__).parent / "credentials").open("r", encoding="utf-8") as file:
    contents = file.readlines()
    if len(contents) != 2:
        print("Error: Credentials file must only contain 2 credentials!", file=sys.stderr)
        raise ValueError

    CLIENT_ID = contents[0].strip()
    CLIENT_SECRET = contents[1].strip()

ENCODED_CLIENT = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode("ascii")).decode("ascii")
SWAPLIST = {
    "they're": "they are",
    "year's": "years",
}

AUTH_TOKEN: Optional[str] = None


@app.route("/auth_callback")
def callback() -> str:
    """
    This function connects with the spotify app.
    """
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
    response = requests.post(url=url, data=data, headers=headers, timeout=600).json()

    global AUTH_TOKEN  # pylint: disable=global-statement
    AUTH_TOKEN = response["access_token"]

    userid = "s11vr90hshxqiw5juux7xiw0n"

    songs = get_songs(SANITIZED_PHRASE)
    print("All songs found!")
    playlist_id, playlist_url = create_playlist(PLAYLIST_NAME, SANITIZED_PHRASE, userid)
    add_to_playlist(songs, playlist_id)

    print(playlist_url)
    os.system(f"open {playlist_url}")
    return ""


def get_page(subphrase: str, track_limit: int, offset: int) -> Optional[Query]:
    """
    Get the page of songs that contain the subphrase in their titles.

    Args:
        subphrase:   The subphrase to be matched within a song title.

        track_limit: The number of songs in the page.

        offset:      The page number.

    Returns:
        The dictionary of matching songs, if any.
    """
    subphrase = subphrase.replace(" ", "%20")
    url = f"https://api.spotify.com/v1/search?q={subphrase}&type=track&limit={track_limit}&offset={offset}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}",
    }
    response = requests.get(url=url, headers=headers, timeout=600).json()
    if "tracks" in response and "items" in response["tracks"]:
        return response["tracks"]["items"]

    return None


def search_songs(subphrase: str) -> Optional[Dict[str, Any]]:
    """
    Find the song, if any, with a name that is an exact match for the provided string.

    Args:
        subphrase:  The subphrase to be matched by a song title.

    Returns:
        The song whose title is an exact match for the subphrase (if any).
    """
    offset = 0
    page = 0
    track_limit = 50  # max value
    while True:
        page_of_results = get_page(subphrase, track_limit, offset)
        if page_of_results is None:
            print(f"\nCannot find: '{subphrase}'")
            return None

        page += 1
        print(f"\rSearching page {page} for '{subphrase}'", end="")
        for song in page_of_results:
            if song["name"].lower() == subphrase:
                print(f'\nFOUND: {song["name"]} by {song["artists"][0]["name"]}')
                return song
        offset += track_limit


def get_songs(phrase: List[str]) -> List[Dict[str, str]]:
    """
    Get the list of songs that, together, make up the given phrase.

    Args:
        phrase: The phrase to be converted into a list of songs.

    Returns:
        The list of songs to match the phrase, with each song represented as a dictionary.
        This dictionary includes information such as track name and artist.
    """
    subphrase = " ".join(phrase)
    songs_to_add: Query = []
    cache: Dict[str, Dict[str, Any]] = {}
    while len(phrase) > 0:
        song: Optional[Dict[str, Any]] = None
        for i in range(0 if len(phrase) <= 5 else len(phrase) - 4, len(phrase)):
            subphrase = " ".join(phrase[:-i] if i != 0 else phrase)
            subphrase = SWAPLIST.get(subphrase, subphrase)
            if subphrase in cache:
                song = cache[subphrase]
                print(f"Using cached result for '{subphrase}'")
            else:
                song = search_songs(subphrase)
            if song is not None:
                phrase = [] if i == 0 else phrase[-i:]
                break
        if song is not None:
            songs_to_add.append(song)
            cache[subphrase] = song
        else:
            break

    return songs_to_add


def create_playlist(playlist_name: str, description: List[str], userid: str) -> Tuple[str, str]:
    """
    Create an empty Spotify playlist.

    Args:
        playlist_name: The playlist title.

        description:   The description for the playlist.

        userid:        The user ID for the account that will own the playlist.

    Returns:
        The unique playlist ID and the playlist's URL.
    """
    print("Creating playlist...")
    url = f"https://api.spotify.com/v1/users/{userid}/playlists"
    data = json.dumps(
        {
            "name": f"{playlist_name}",
            "description": f"{' '.join(description)}",
            "public": True,
        }
    )
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}",
    }

    response = requests.post(url=url, data=data, headers=headers, timeout=600).json()
    playlist_id = response["id"]
    playlist_url = response["external_urls"]["spotify"]

    return playlist_id, playlist_url


def add_to_playlist(songs: List[Dict[str, str]], playlist_id: str) -> None:
    """
    Append a pre-existing Spotify playlist.

    Args:
        songs:       The list of songs to add to the playlist.
                     Each song must be represented as a dictionary containing
                     the song's URI, in the <key>: <value> form of:
                     "uri": <value>.

        playlist_id: The unique ID of the playlist to append.

    Raises:
        ValueError: If Spotify returns an error when attempting to update
                    the playlist.
    """
    print("Adding songs to playlist...")
    uris = ",".join([song["uri"] for song in songs])
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?uris={uris}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}",
    }
    response = requests.post(url=url, headers=headers, timeout=600)
    if "error" in response.json():
        raise ValueError


def main() -> int:
    global PLAYLIST_NAME
    global SANITIZED_PHRASE
    if len(sys.argv) != 3:
        print(
            """
Usage:
    python3 main.py "phrase" "playlist name"
        """
        )

    PLAYLIST_NAME = sys.argv[1]  # pylint: disable=invalid-name
    user_phrase = sys.argv[2].lower()  # pylint: disable=invalid-name

    # Filter out non-alphabetical characters
    SANITIZED_PHRASE = "".join(
        [x for x in user_phrase if (ord(x) >= ord("a") and ord(x) <= ord("z")) or x == " " or x == "'"]
    ).split()

    os.system(
        "open https://accounts.spotify.com"
        f"/authorize?response_type=code\\&client_id={CLIENT_ID}"
        "\\&scope=playlist-modify-public"
        "\\&redirect_uri=http://localhost:8509/auth_callback"
        "\\&state=ramranch"
    )

    app.run(port=8509, host="0.0.0.0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
