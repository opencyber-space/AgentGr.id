from core.k8s import AgentsUpdateNotifier

def update(data):
    print(data)

notifier = AgentsUpdateNotifier(on_instances_update=update)
notifier.start(block_id="uppercase-001")

if __name__ == "__main__":
    import time
    while True:
        time.sleep(30)