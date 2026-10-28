# Installation and execution

## Reference environment

The project was developed on Ubuntu 24.04 with Python 3.11 and ROS 2 Humble through RoboStack/Pixi. `pixi.toml` defines three environments: `ros` for the framework and bridge, `carla` for simulator clients and `ml` for model exploration. Running the framework requires the `ros` environment, the simulator and a VLM service.

The Pixi configuration specifies Linux x86-64, glibc ≥ 2.31 and CUDA 12.8. The experimental machine had an NVIDIA RTX 5050 Laptop GPU with 8 GB VRAM and 32 GB RAM; this describes the platform used, rather than a validated hardware minimum. The `ml` environment is optional and does not start an inference server.

## Set up the project

1. Install Pixi and CARLA **0.9.16** separately. The Python client pinned in `pixi.toml` must match the simulator server.
2. Open a terminal at the repository root and run:

   ```bash
   cp .env.example .env
   pixi install -e ros --locked
   pixi run -e ros build_bridge
   ```

3. Set the CARLA installation path in the terminal that will start the simulator:

   ```bash
   export CARLA_ROOT=/path/to/carla_0.9.16
   ```

ROS dependencies are included as source; their provenance is documented in [THIRD_PARTY.md](../THIRD_PARTY.md). No additional `git clone` is required. The build uses Python from the active environment. `ros_ws/build`, `install` and `log` are local build products and must be regenerated if the checkout is moved.

## Configure the VLM provider

For local inference, start Ollama and download the multimodal model:

```bash
ollama pull qwen3.5:2b
```

The service should listen on `http://localhost:11434`; set `OLLAMA_API_URL` to change the endpoint. The framework uses Ollama's native API.

For OpenRouter, set `OPENROUTER_API_KEY` in `.env` and run:

```bash
pixi run -e ros launch llm_provider:=openrouter llm_model:=anthropic/claude-haiku-4.5
```

For OpenAI, set `OPENAI_API_KEY` and select a model that accepts images:

```bash
pixi run -e ros launch llm_provider:=openai llm_model:=gpt-4o
```

These are the identifiers configured in the project; their current service availability has not been checked. Keys are read from the environment or `.env` and must never be published. During a full launch, `llm_provider` and `llm_model` arguments override `.env`; the defaults are Ollama and `qwen3.5:2b`. Individual node execution uses the `.env` values. The legacy `ros_ws/.env` location is also supported. Set `TFM_ENV_FILE` to select a file explicitly.

## Start the simulation

Use separate terminals at the repository root:

```bash
# Terminal 1
pixi run carla
# Windowed alternative: pixi run carla_window
```

```bash
# Terminal 2
pixi run -e ros launch
```

```bash
# Terminal 3, after the Traffic Manager configuration messages appear
pixi run -e ros demo --scenario traffic
```

The bridge configuration uses `Town10HD`, with a fixed spawn point for the `hero` vehicle. The installed sensor definition comes from `ros_ws/src/low_control_module/launch/objects.json`. Changing the map also requires adapting the spawn point. The scenario script creates background and scenario-specific actors, leaves ego driving to the framework and destroys its actors on Ctrl-C.

The launch preserves delays of 10 s for spawning, 160 s for perception, 165 s for decision-making and 175 s for control, measured from launch startup. These are fixed delays rather than readiness checks. They can be changed:

```bash
pixi run -e ros launch spawn_delay:=10.0 perception_delay:=30.0 decision_delay:=35.0 control_delay:=45.0
```

For a remote server:

```bash
pixi run -e ros launch host:=192.168.1.10 port:=2000 timeout:=20
pixi run -e ros demo --host 192.168.1.10 --port 2000 --scenario traffic
```

Traffic Manager uses port 8000. Sensors and topics expect the `hero` role.

## Scenarios and visualization

```bash
pixi run -e ros demo --scenario free
pixi run -e ros demo --scenario traffic --vehicles 15
pixi run -e ros demo --scenario obstacle
pixi run -e ros demo --scenario pedestrian
pixi run -e ros demo --scenario ambulance
```

Run one scenario at a time and reset the world/ego between comparable trials. `free` requests no background vehicles; other scenarios request 15 by default. The actual number spawned depends on available spawn points. `--seed` controls Python initialization; it does not guarantee identical trajectories in an asynchronous simulation.

To open RViz or inspect topics with the overlay loaded:

```bash
pixi run -e ros bash scripts/ros.sh rviz2 -d config/rviz2.rviz
pixi run -e ros bash scripts/ros.sh ros2 topic echo /llm/output
pixi run -e ros bash scripts/ros.sh ros2 topic echo /action_committed
```

`pixi run -e ros source_bridge` opens a shell with the overlay sourced. `read_transform` prints a lane-centered spawn point. `spawn_objects`, `ros_bridge` and `manual_control` support separate execution; avoid starting duplicate processes when the full launch is already running.

## Outputs and troubleshooting

Raw responses and per-call context are saved to `outputs/output_<timestamp>.md`. Set `TFM_OUTPUT_DIR` to change the destination. To capture stdout and stderr while preserving the launch exit status:

```bash
mkdir -p outputs
set -o pipefail
pixi run -e ros launch 2>&1 | tee outputs/run.log
```

`launch_log` captures a Haiku run in `outputs/haiku.log`; reusing the task overwrites that log. For evaluation campaigns, choose a unique filename and record the provider, model, scenario, seed and configuration.

If the bridge cannot connect, check simulator readiness, the server address and matching CARLA versions. If `hero` is missing, check the spawn point and whether it is occupied. If the model does not respond, check the local service or cloud credentials; the controller requests reduced speed after 8 s without a valid decision. Full operation requires an active simulator and VLM: tests without the simulator do not validate driving behavior.
