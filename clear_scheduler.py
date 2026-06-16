import subprocess
import sys

def clear_solo_tasks():
    print("🗑️ Searching for scheduled tasks containing 'SOLO'...")
    
    # We use PowerShell's native cmdlets directly through Python's subprocess
    ps_command = "Get-ScheduledTask -TaskName *SOLO* -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false"
    
    result = subprocess.run(["powershell", "-Command", ps_command], capture_output=True, text=True)
    
    # Check if the command was successful
    if result.returncode == 0:
        print("✅ Successfully cleared all SOLO tasks from the Windows Task Scheduler.")
        print("   Run 'SchTasks /Query | findstr SOLO' to verify the queue is empty.")
    else:
        print(f"❌ FAILED to delete tasks.")
        print("   ⚠️ Ensure you are running this terminal as Administrator!")
        if result.stderr:
            print(f"   Error details: {result.stderr.strip()}")

if __name__ == "__main__":
    clear_solo_tasks()