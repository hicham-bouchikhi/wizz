# Wizz for Discord

Send `~wizz @UserName` in a server text channel. The mentioned person must already
be in a regular voice channel. The bot creates two private temporary voice rooms,
moves them between the rooms about once a second for five seconds, returns them to
their original room, and deletes the temporary rooms. It doesn't need to join voice
or play audio.

Anyone who can send commands to the bot can use it. There is a 30-second cooldown
per caller and target, and only one wizz can run per server at a time. If someone
disconnects or moves out of the temporary rooms, the bot stops moving them.

## Discord configuration

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications).
   On its **Bot** page, enable **Message Content Intent** and get the bot token.
   Server Members Intent and Presence Intent are not needed.
2. In **OAuth2 → URL Generator**, select the `bot` scope and these permissions:
   **View Channels**, **Send Messages**, **Read Message History**, **Manage Channels**,
   **Connect**, and **Move Members**. Open the generated URL to invite it to your server.
   Ensure channel overwrites also allow these permissions in the command and original
   voice channels. Administrator is not required.

## Deploy directly from GitHub with Portainer

Use a **Docker Standalone** environment in Portainer. This stack builds its image
from the repository's Dockerfile; Docker Swarm requires a separately published
image and is not supported by this setup.

1. Open your Docker environment, choose **Stacks → Add stack**, and name it `wizz`.
2. Choose **Git Repository**. On newer Portainer versions, create or select a Git
   **Source** first. Use these settings:

   | Setting | Value |
   | --- | --- |
   | Repository URL | `https://github.com/hicham-bouchikhi/wizz` |
   | Repository reference | `refs/heads/main` |
   | Compose path | `compose.yaml` |
   | Repository authentication | Off (the repository is public) |

3. Under **Environment variables**, add `DISCORD_TOKEN` with your actual Discord
   bot token. Keep the token in Portainer; do not commit it to GitHub.
4. Click **Deploy the stack**. The first deployment builds the Python image and
   installs its dependencies, so allow a few minutes.
5. Open the stack's `wizz` container and view **Logs**. Once it says `Logged in as ...`,
   use `~wizz @UserName` in Discord while the target is connected to voice.

The Docker host needs internet access to GitHub, Docker Hub, PyPI, and Discord.
No published ports, volume mounts, GitHub credentials, or local `.env` file are
needed for this Portainer deployment. The Discord permissions and Message Content
Intent described above still need to be configured.

Portainer reference: [deploying a stack from a Git repository](https://docs.portainer.io/user/docker/stacks/add#option-3-git-repository).

## Run with Docker

Install Docker Engine with Docker Compose, or Docker Desktop. Configure the Discord
app above, then create a `.env` file next to `compose.yaml` containing:

```env
DISCORD_TOKEN=your_actual_bot_token
```

Keep this file private. The token is supplied at runtime and is excluded from the
image's build context.

From the project directory, build and start the bot in the background:

```bash
docker compose up -d --build
```

Check whether it is running and follow its logs:

```bash
docker compose ps
docker compose logs -f wizz
```

Once it logs `Logged in as ...`, join a voice channel and use `~wizz @UserName` in
a text channel. `~help wizz` shows the command's help. Closing the terminal leaves
the container running. The bot restarts after failures and when Docker starts,
unless you explicitly stop it. Keep Docker and the host machine running.

Stop the bot with:

```bash
docker compose down
```

Docker sends SIGINT and allows 30 seconds for voice restoration and room cleanup.
No incoming ports or data volumes are required; the bot connects out to Discord.
Run one instance per bot token. Stop any directly running Python instance before
starting the container.

After editing the code or updating the token, run `docker compose up -d --build`
again. Compose recreates the service when the image or configuration changes.

Docker reference: [Compose startup](https://docs.docker.com/get-started/docker-concepts/running-containers/multi-container-applications/),
[restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/),
[environment interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/).

## Run directly with Python

1. Install Python 3.10 or newer and configure the Discord app above.
2. Prepare the project:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   cp .env.example .env
   ```

   On Windows, activate with `.venv\Scripts\activate` instead.

3. Edit `.env` and replace `your_bot_token_here` with your token. Keep this file private.
4. Start the bot:

   ```bash
   python bot.py
   ```

5. Join a voice channel, then send `~wizz @UserName` from a text channel the bot can read.
   `~help wizz` shows the command's help.

Discord network latency and rate limits can extend the five-second duration;
the bot respects API rate limits. Restoration and cleanup also run after a failed
move or a normal shutdown. If restoration fails, occupied rooms are retained to
avoid disconnecting anyone, and the bot reports the problem. A forced process kill
or machine crash can leave temporary rooms behind; move their occupants back and
delete those rooms manually before restarting.

## Checks

```bash
python -m unittest discover -s tests -v
```

The tests simulate Discord. A live test requires your bot token and a server.

API references: [discord.py](https://discordpy.readthedocs.io/en/stable/),
[message content intent](https://discordpy.readthedocs.io/en/stable/intents.html#message-content),
[Discord member movement permissions](https://docs.discord.com/developers/resources/guild#modify-guild-member).
