# SNTalkBot

> **SNTalkBot 5.1.4:** role-isolated Full/Player/Manager operation, queue provenance and playlist sessions, Related Radio, bundled default YouTube cookies, a role-aware `status` dashboard, bounded Manager/Full `events`, and event-driven moderation for user/channel metadata updates.


Registered commands are prefix-free in both private and channel/broadcast messages (for example `h`, `p song`, `ap on`). A leading `/` remains accepted only for backward compatibility. Admins can disable normal channel-text reactions with `ci off`; an enabled `filter` still moderates received text before the channel-input gate, and `cm on|off|status` independently controls Player announcements sent to the channel.


> **Platform:** Linux/Docker only. Windows GUI support has been removed intentionally.


SNTalkBot is a Linux/Docker-ready TeamTalk bot combining server administration, moderation, media playback, YouTube/YouTube Music queues, TTS announcements, localization, and multi-instance deployment support.

The project can run in three instance modes:

- **Full Bot** — player + server management
- **Player Bot** — media/player features without server-management commands
- **Server Manager** — server-management features without the music player

Runtime event integration uses TeamTalk user/channel/server/file/state callbacks rather than polling. `status` is available in every role; `events [1-25]` is registered only in Manager/Full and stores a bounded in-memory audit trail without raw command arguments or secrets.

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
TTU_TAG=2026.08.23-r6 ./publish.sh
```

## License and upstream attribution

This combined main project is distributed under GPL-2.0 because its TTUtilities upstream is GPL-2.0. See `LICENSE` and `NOTICE.md`. MIT notices for adapted TTMediaBot components are preserved under `THIRD_PARTY_LICENSES/`.


## 2026.08.23-r6

Startup/reconnect welcome replays are suppressed, intentional short aliases are resolved without duplicate handlers, Player-only cache/message commands are isolated from Manager-only mode, and long-message/async-user edge cases are hardened. FIFO Player TTS, standard gTTS, no-music-ducking, and `dr` remain available. See `README_TH.md` and `RELEASE_NOTES_TH.md`.

## Player TTS and music mixing

Player announcements use a separate audio stream mixed with music by PulseAudio. Announcements **do not lower, pause, or duck music**. The FIFO queue still prevents TTS announcements from overlapping each other.

## Official developer reports

`dr <message>` sends an explicit bug report, problem report, feature request, or suggestion through the official developer relay. The public bot does not expose relay credentials or require users to open a separate support URL.
