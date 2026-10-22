from core.his import HisClient
import time
import json


BASE_URL = "http://35.223.239.192:30608"


def main():
    client = HisClient(
        base_url=BASE_URL,
        poll_interval=1.0,
        max_wait=60,
    )



    print("\nSubmitting job (fire & forget)...")

    obj = client.submit(
        input_data={
            "task": "classify",
            "text": "Kubernetes simplifies deployment",
        },
    )

    print("Submitted:")
    print(json.dumps(obj.__dict__, indent=2))

    response_id = obj.id



    print("\nPolling until completed...")

    while True:
        result = client.check_and_get_response(response_id)
        if result:
            print("Completed:")
            print(json.dumps(result.__dict__, indent=2))
            break
        else:
            print("Still processing...")
            time.sleep(1)

   

    print("\nSubmit and wait example...")

    obj = client.submit_and_wait(
        input_data={
            "task": "summarize",
            "text": "Artificial Intelligence enables machines to think.",
        },
    )

    print("Final Response:")
    print(json.dumps(obj.__dict__, indent=2))


if __name__ == "__main__":
    main()
