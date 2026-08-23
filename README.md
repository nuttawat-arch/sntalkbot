# SNTalkBot

> **Platform:** Linux/Docker only. Windows GUI support has been removed intentionally.


SNTalkBot is a Linux/Docker-ready TeamTalk bot combining server administration, moderation, media playback, YouTube/YouTube Music queues, TTS announcements, localization, and multi-instance deployment support.

The project can run in three instance modes:

- **Full Bot** — player + server management
- **Player Bot** — media/player features without server-management commands
- **Server Manager** — server-management features without the music player

For the complete Thai documentation, see [`README_TH.md`](README_TH.md).

## Quick Docker Hub publish

```bash
docker login
./publish.sh
```

Default image:

```text
nuttawat0295/sntalkbot:latest
```

Use a versioned tag for safer rollback:

```bash
TTU_TAG=2026.08.23-r2 ./publish.sh
```

## License and upstream attribution

This combined main project is distributed under GPL-2.0 because its TTUtilities upstream is GPL-2.0. See `LICENSE` and `NOTICE.md`. MIT notices for adapted TTMediaBot components are preserved under `THIRD_PARTY_LICENSES/`.


## 2026.08.23-r2

Player announcements are now serialized through a FIFO TTS queue, Player and Manager TTS controls are separated, duplicate command aliases were removed, and `/dr` adds optional Telegram direct reporting. See `README_TH.md` and `RELEASE_NOTES_TH.md`.
