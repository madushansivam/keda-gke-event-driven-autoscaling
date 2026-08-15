"""
Consumer: pulls messages from a Pub/Sub subscription and processes them.
Simulates realistic variable work time instead of an instant ack —
this makes autoscaling behavior visible and believable.
"""
import os
import time
import random
from concurrent.futures import TimeoutError
from google.cloud import pubsub_v1

PULL_TIMEOUT_SECONDS = 3.0

def get_config():
    return {
        "project_id": os.environ["PUB_SUB_PROJECT"],
        "subscription_name": os.environ["PUB_SUB_SUBSCRIPTION"],
    }

def simulate_work():
    # Randomized delay to mimic real processing (e.g. image resize, DB write)
    duration = random.uniform(0.5, 2.5)
    time.sleep(duration)
    return duration

def make_callback():
    def callback(message):
        duration = simulate_work()
        print(f"Processed {message.data} in {duration:.2f}s")
        message.ack()
    return callback

def consume_once(project_id, subscription_name, timeout):
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(project_id, subscription_name)
    print(f"Listening on {subscription_path}")
    future = subscriber.subscribe(subscription_path, callback=make_callback())
    with subscriber:
        try:
            future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            future.result()

if __name__ == "__main__":
    config = get_config()
    while True:
        consume_once(config["project_id"], config["subscription_name"], PULL_TIMEOUT_SECONDS)
        time.sleep(2)
