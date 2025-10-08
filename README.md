# Aidbox Fhir Chat

A local instance of Aidbox run via docker compose with an additional OpenAI chat interface.

## Aidbox Setup

Startup the local Aidbox instance:

```bash
docker compose up
```

### Aidbox Account

You will need to create a (free) account with [Aidbox](https://aidbox.app). When starting the server for the first time,
you will login to this account before using the local Aidbox instance. Once this is done, a license is generated for
you, linked to your account, and associated with your server instance. The license is free, and there are no
restrictions to the number of licenses you can have.

### Loading Patient Data

Visit the [console](http://localhost:8080/ui/console) and click on the link in the box labeled "Import Synthetic Dataset"

### Basic Authorization

This is optional, but needed if you want to access the Aidbox instance outside of this app.

* go to IAM > Client and create a new client
* from the UI console, go to IAM > Basic Auth
* enter client id and secret of your choice
* use the three Run buttons to:
    - update the client with the secret
    - create the access policy
    - test the connection
* use the resulting "Authorization: Basic [encoded secret]"

The encoded secret is equivalent to:

```
echo "basic:secret | base64
```

But doing the above from the command line, it's different by one or two characters at the end, so you have to go with
the output from the UI Console.

### Postman

Choose Basic Auth, and use the id and secret for username and password (respectively).

### Queries

```
export AIDBOX_TOKEN=YmFzaWM6c3VwZXJzZWNyZXQ=
curl --location "http://localhost:8080/fhir/Patient?_format=json" \
  --header "Authorization: Basic $AIDBOX_TOKEN"

```

## MCP Server

The docker-compose file includes the configuration for running an mcp server. There's additional
[documentation](https://www.health-samurai.io/docs/aidbox/modules/other-modules/mcp#mcp) about configuration, but to get
started, enable all access to the mcp endpoint with this policy:

``` json
{
  "resourceType": "AccessPolicy",
  "id": "allow-mcp-endpoints",
  "link": [
    {
      "id": "mcp",
      "resourceType": "Operation"
    },
    {
      "id": "mcp-sse",
      "resourceType": "Operation"
    },
    {
      "id": "mcp-client-messages",
      "resourceType": "Operation"
    }
  ],
  "engine": "allow"
}

```

You can add this policy via Aidbox > IAM > AccessPolicy and click "Create +" see
(http://localhost:8080/ui/console#/iam/auth/AccessPolicy/new?tab=raw&create=true)

### Using the Console

You can interact with the Aidbox mcp server via an ipython session:

```bash
uv run ipython -i src/utils/console.py
```

Then from then console session, list the available tools:

```bash
await list_tools()
```

Or get the details for a specific one:

```bash
await get_tool([name])
```

### Configuring Claude Code

As as simple example, you can use Claude to interface with the server.

You'll need `supergateway` as a dependency:

```bash
npm install -g supergateway
```

Then add the mcp server to Claude:

```bash
claude mcp add aidbox-mcp -- npx -y supergateway --sse http://localhost:8080/sse
```

Then start a new Claude session and run:

```bash
/mcp reconnect aidbox-mcp
```

Start asking questions! For example, "Using aidbox-mcp, can you tell me who the oldest living patient is?"

#### Notes

Claude is using [supergateway](https://www.npmjs.com/package/supergateway) under the hood to interact with the mcp
server. From `~/.claude.json` you can see:

```bash
"mcpServers": {
  "aidbox-mcp": {
    "type": "stdio",
    "command": "npx",
    "args": [
      "-y",
      "supergateway",
      "--sse",
      "http://localhost:8080/sse"
    ],
    "env": {}
  }
}
```

## Chat App

### Configuring

Copy the `env-sample.txt` to the environment management tool of your choice. (I use [direnv](https://direnv.net/))

```bash
cp env-sample.txt .env
direnv allow
```

### Chatting with Aidbox

You can start a chat session that uses an OpenAI gpt model along with the mcp sever that provides a conversational
interface to the Aidbox instance.

To start up the chat:

```bash
uv run scripts/chat.py  
```

You can pull a patient identifier from Aidbox by going to the [list of patients](http://localhost:8080/ui/console#/resource-types/Patient).
Copy any one of the identifiers and ask the agent:

> "Can you tell me about patient 123?"

The agent will keep context, so you can ask follow up questions such as:

> "Can you provide me a summary of their last clinical encounter and include all current medications and conditions."
