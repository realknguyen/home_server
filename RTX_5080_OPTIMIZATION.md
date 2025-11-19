# Ollama RTX 5080 Optimization Guide

## Current Configuration

Your Ollama setup is now optimized for the RTX 5080 with the following settings:

### Key Performance Settings

| Setting                      | Value                   | Description                                                  |
| ---------------------------- | ----------------------- | ------------------------------------------------------------ |
| **OLLAMA_NUM_CTX**           | 32768 (64K in GPU mode) | Context window size - how much text the model can "remember" |
| **OLLAMA_NUM_PARALLEL**      | 4                       | Number of parallel requests handled simultaneously           |
| **OLLAMA_MAX_LOADED_MODELS** | 2                       | Keep 2 models in VRAM at once (adjust based on model sizes)  |
| **OLLAMA_NUM_BATCH**         | 512                     | Batch size for processing (larger = faster on RTX 5080)      |
| **OLLAMA_KEEP_ALIVE**        | 30m                     | Keep models loaded in VRAM for 30 minutes                    |
| **OLLAMA_NUM_GPU**           | 999                     | Use all available GPU layers                                 |
| **OLLAMA_FLASH_ATTENTION**   | 1                       | Enable flash attention for 2-4x faster inference             |

## VRAM Usage by Model Size

With RTX 5080's 16GB VRAM, here's approximate usage:

| Model Size    | VRAM Usage | Context 32K | Context 64K | Recommended              |
| ------------- | ---------- | ----------- | ----------- | ------------------------ |
| 7B params     | ~4-5 GB    | ✅ Yes      | ✅ Yes      | ⭐ Best performance      |
| 13B params    | ~8-9 GB    | ✅ Yes      | ✅ Yes      | ⭐ Recommended           |
| 30-34B params | ~18-20 GB  | ⚠️ Tight    | ❌ No       | Use 16K context          |
| 70B params    | ~40+ GB    | ❌ No       | ❌ No       | Too large for single GPU |

## Tuning Recommendations

### For Maximum Throughput (Multiple Users)

```bash
OLLAMA_NUM_PARALLEL=6-8           # More parallel requests
OLLAMA_MAX_LOADED_MODELS=1        # Single model for max throughput
OLLAMA_NUM_CTX=16384             # Reduce context to save VRAM
```

### For Maximum Context Length (Long Documents)

```bash
OLLAMA_NUM_CTX=131072            # 128K context (if model supports)
OLLAMA_NUM_PARALLEL=1            # Single request for max VRAM
OLLAMA_MAX_LOADED_MODELS=1       # Single model
OLLAMA_NUM_BATCH=256             # Smaller batch
```

### For Development/Testing (Fast Model Switching)

```bash
OLLAMA_KEEP_ALIVE=5m             # Unload models quicker
OLLAMA_MAX_LOADED_MODELS=3       # Keep more models ready
OLLAMA_NUM_CTX=8192              # Moderate context
```

## Performance Tips

1. **First Run Optimization**

   - First inference is slower (model loading)
   - Subsequent requests are much faster
   - `KEEP_ALIVE` keeps models "warm"

2. **Monitor VRAM Usage**

   ```bash
   nvidia-smi -l 1  # Monitor GPU usage in real-time
   ```

3. **Recommended Models for RTX 5080**

   - **Llama 3.1 8B**: Blazing fast, excellent for chat
   - **Llama 3.1 13B**: Best balance of speed/quality
   - **Mistral 7B**: Very fast, great for coding
   - **Yi 34B**: Maximum quality that fits (with optimizations)

4. **Temperature Optimization**
   - Keep GPU cool for sustained performance
   - RTX 5080 will throttle if temps exceed 83°C

## Testing Your Setup

```bash
# Pull a model
docker exec ollama ollama pull llama3.1:8b

# Test inference speed
time docker exec ollama ollama run llama3.1:8b "Write a short story"

# Check what's loaded
docker exec ollama ollama ps

# View logs
docker logs ollama -f
```

## Troubleshooting

### Out of Memory Errors

- Reduce `OLLAMA_NUM_CTX` to 16384 or 8192
- Reduce `OLLAMA_NUM_PARALLEL` to 2
- Use smaller model (7B instead of 13B)

### Slow Performance

- Ensure GPU mode is active: `docker logs ollama | grep -i gpu`
- Check if using CPU fallback: `nvidia-smi`
- Increase `OLLAMA_NUM_BATCH` to 1024

### Models Not Staying Loaded

- Increase `OLLAMA_KEEP_ALIVE` to `1h` or `24h`
- Check available VRAM with `nvidia-smi`

## Environment Variables Reference

Full list of Ollama environment variables:

- `OLLAMA_HOST`: Network bind address (0.0.0.0 for all interfaces)
- `OLLAMA_PORT`: API port (default 11434)
- `OLLAMA_NUM_PARALLEL`: Parallel request limit
- `OLLAMA_MAX_LOADED_MODELS`: Max models in VRAM
- `OLLAMA_NUM_CTX`: Context window size (tokens)
- `OLLAMA_NUM_BATCH`: Processing batch size
- `OLLAMA_NUM_GPU`: GPU layer count (999 = all)
- `OLLAMA_KEEP_ALIVE`: Model persistence duration
- `OLLAMA_FLASH_ATTENTION`: Enable flash attention
- `OLLAMA_MAX_VRAM`: Max VRAM usage (0 = unlimited)
- `OLLAMA_GPU_OVERHEAD`: GPU memory overhead (bytes)

## Monitoring Commands

```bash
# GPU utilization
nvidia-smi dmon -s pucvmet

# Memory usage
docker stats ollama

# API metrics
curl http://localhost:11434/api/tags

# Test with different context sizes
curl -X POST http://localhost:11434/api/generate -d '{
  "model": "llama3.1:8b",
  "prompt": "Hello",
  "options": {"num_ctx": 32768}
}'
```

Enjoy your optimized Ollama setup! 🚀
