# CodeMap

## Local project import

You can now import your own codebase from a **directory path or ZIP archive**. Review the included/excluded files before starting Business Components or Function Call analysis. Chat and explanations use the same approved source snapshot.

Start the Python 3.10+ local service with `python server/app.py --root /path/to/projects`, then run `npm ci` and `npm run dev` in `frontend`. Open **http://127.0.0.1:5173**. Configure `OPENAI_API_KEY` and `OPENAI_MODEL` in the service environment for analysis; preview works without them. Credentials stay on the server.

See [Project import setup, Windows/WSL paths, limits and tests](docs/project-import.md) for complete instructions. The legacy Assistant setup below is retained as historical prototype documentation and is not used by the new application flow.

## Overview

CodeMap is an interactive tool designed to aid individuals in learning new projects, onboarding onto codebases, and understanding source code structures. It provides an engaging and visual approach with interactive graphs, detailed descriptions, and overviews to enhance comprehension. Integrated with ChatGPT, users can gain deeper insights and context about the code while browsing.

## Features

- **Interactive Graphs**: Visual representations of code structure with clickable components for detailed exploration.
- **Descriptions & Overviews**: Contextual information to help users understand various parts of the codebase.
- **ChatGPT Integration**: Built-in ChatGPT functionality for real-time assistance and explanations.

## Prerequisites

Before you get started, ensure you have the following installed:

1. **Node.js**

   Download and install Node.js from the [official Node.js website](https://nodejs.org/). Follow the installation instructions for your operating system.

2. **OpenAI API Key**

   To use the ChatGPT integration, you need an OpenAI API key. Sign up at [OpenAI](https://beta.openai.com/signup/) and obtain your API key.

## Getting Started

To run CodeMap locally, follow these steps:

1. **Install Dependencies**:
```bash
cd CodeMap/frontend
npm install
```
2. **Create a .env File: In the root directory of frontend folder, create a .env file and add your OpenAI API Key:**
```bash
// .env
VITR_API_KEY=your_api_key_here
```

3. **Start Application**
```bash
npm start
```

## File Structure

The project is organized as follows:
```bash
src/
└── gpt/
└── frontend/
    ├── components/          
    └── features/              
        └── codemapper/               
            ├── business-components/
            └── function-call/
    └── ...
```

## Tech Stack

**Client:** React, TailwindCSS, NodeJS

**Server:** No server side code

## Project Status

## Related Papers
