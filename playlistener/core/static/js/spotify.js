const PLAYLIST_URL_PREFIX = "https://open.spotify.com/playlist/";

window.addEventListener("load", () => {
  for (const input of document.getElementsByClassName("playlist-id")) {
    input.addEventListener("input", () => {
      let value = input.value;
      if (value.startsWith(PLAYLIST_URL_PREFIX)) {
        value = value.substring(PLAYLIST_URL_PREFIX.length);
      }
      if (value.indexOf("?") !== -1) {
        value = value.substring(0, value.indexOf("?"));
      }
      input.value = value;
      const a = input.previousElementSibling.getElementsByClassName("playlist-link")[0];

      if (value.length > 0) {
        a.href = `https://open.spotify.com/playlist/${value}`;
      } else {
        a.removeAttribute("href");
      }
    });
  }
});
