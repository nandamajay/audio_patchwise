from app.knowledge.seed import run_seed


if __name__ == "__main__":
    result = run_seed(subsystem="alsa-asoc", months=24)
    print(result)
