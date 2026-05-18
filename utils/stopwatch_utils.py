import time

class Stopwatch:
    def __init__(self):
        self.start_time = None
        self.running = False

    def start(self):
        if not self.running:
            self.start_time = time.time()
            self.running = True

    def stop(self):
        if self.running:
            elapsed_time = time.time() - self.start_time
            self.running = False
            return self.format_time(elapsed_time)
        return "00:00:00.000"

    def format_time(self, elapsed):
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        milliseconds = int((elapsed % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

# # Example usage
# stopwatch = Stopwatch()

# # Start the stopwatch
# stopwatch.start()
# # Simulate a process
# time.sleep(2)  

# # Stop the stopwatch and get time taken
# time_taken = stopwatch.stop()
# print("Time taken:", time_taken)
