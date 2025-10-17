import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
try:
    import paramiko
except ImportError:
    print("Dependency 'paramiko' is not installed. Install it with: pip install paramiko")
    sys.exit(1)

def create_remote_directory_recursive(sftp, remote_path):
    """
    Creates a remote directory recursively if it doesn't exist.
    
    :param sftp: SFTP client object.
    :param remote_path: Path on the SFTP server.
    """
    dirs = []
    path = remote_path
    
    # Build list of directories to create
    while path and path != '/':
        dirs.append(path)
        path = os.path.dirname(path)
    
    # Create directories from top to bottom
    for dir_path in reversed(dirs):
        try:
            sftp.stat(dir_path)
        except FileNotFoundError:
            try:
                sftp.mkdir(dir_path)
                print(f"Created directory: {dir_path}")
            except Exception as e:
                print(f"Failed to create directory {dir_path}: {e}")


def _normalize_remote_path(*parts: str) -> str:
    """Join remote path parts with forward slashes and normalize duplicates."""
    joined = "/".join(p.strip("/") for p in parts if p is not None and p != "")
    if parts and str(parts[0]).startswith("/"):
        return "/" + joined
    return joined

def upload_to_sftp(local_path, sftp, remote_base_path, progress_callback=None):
    """
    Uploads files and directories to an SFTP server while maintaining the folder structure.

    :param local_path: Path to the local file or directory.
    :param sftp: SFTP client object.
    :param remote_base_path: Base path on the SFTP server.
    :param progress_callback: Optional callback function for progress updates.
    """
    local_path = os.path.abspath(local_path)
    
    if os.path.isdir(local_path):
        # Get the directory name to create on remote
        dir_name = os.path.basename(local_path)
        remote_dir_path = _normalize_remote_path(remote_base_path, dir_name)
        
        # Create remote directory
        create_remote_directory_recursive(sftp, remote_dir_path)
        
        # Recursively upload directory contents
        for root, dirs, files in os.walk(local_path):
            # Calculate relative path from the source directory
            rel_path = os.path.relpath(root, local_path)
            
            if rel_path == '.':
                remote_current_dir = remote_dir_path
            else:
                remote_current_dir = _normalize_remote_path(remote_dir_path, rel_path.replace(os.sep, '/'))
                create_remote_directory_recursive(sftp, remote_current_dir)
            
            # Upload files in current directory
            for file in files:
                local_file = os.path.join(root, file)
                remote_file = _normalize_remote_path(remote_current_dir, file)
                
                try:
                    sftp.put(local_file, remote_file)
                    if progress_callback:
                        progress_callback(f"Uploaded: {local_file} -> {remote_file}")
                    else:
                        print(f"Uploaded: {file}")
                except Exception as e:
                    print(f"Failed to upload {file}: {e}")
    else:
        # Upload a single file
        file_name = os.path.basename(local_path)
        remote_file_path = _normalize_remote_path(remote_base_path, file_name)

        # Ensure remote directory exists
        remote_dir = os.path.dirname(remote_file_path)
        create_remote_directory_recursive(sftp, remote_dir)

        try:
            sftp.put(local_path, remote_file_path)
            if progress_callback:
                progress_callback(f"Uploaded: {local_path} -> {remote_file_path}")
            else:
                print(f"Uploaded: {file_name}")
        except Exception as e:
            print(f"Failed to upload {file_name}: {e}")


def upload_files_list(files, sftp, remote_base_path, progress_callback=None, base_dir: str | None = None):
    """
    Upload a list of files while preserving relative structure from base_dir.
    If base_dir is None, the common parent of all files is used.
    """
    files = [os.path.abspath(f) for f in files]
    if not files:
        return
    if base_dir is None:
        try:
            base_dir = os.path.commonpath(files)
        except ValueError:
            # Different drives on Windows; fall back to first file's parent
            base_dir = os.path.dirname(files[0])
    base_dir = os.path.abspath(base_dir)

    for local_file in files:
        if not os.path.isfile(local_file):
            # Skip non-files silently
            continue
        rel_path = os.path.relpath(local_file, base_dir).replace(os.sep, "/")
        remote_path = _normalize_remote_path(remote_base_path, rel_path)
        remote_dir = os.path.dirname(remote_path)
        create_remote_directory_recursive(sftp, remote_dir)
        try:
            sftp.put(local_file, remote_path)
            if progress_callback:
                progress_callback(f"Uploaded: {local_file} -> {remote_path}")
            else:
                print(f"Uploaded: {local_file}")
        except Exception as e:
            print(f"Failed to upload {local_file}: {e}")

def show_upload_confirmation(file_path):
    """
    Shows a confirmation dialog before uploading.
    """
    root = tk.Tk()
    root.withdraw()
    
    file_name = os.path.basename(file_path)
    file_type = "folder" if os.path.isdir(file_path) else "file"
    
    result = messagebox.askyesno(
        "Confirm Upload",
        f"Upload {file_type}: '{file_name}' to SFTP server?\n\nPath: {file_path}",
        icon='question'
    )
    
    root.destroy()
    return result

def show_progress_window():
    """
    Shows a progress window during upload.
    """
    root = tk.Tk()
    root.title("SFTP Upload Progress")
    root.geometry("500x200")
    
    # Center the window
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (500 // 2)
    y = (root.winfo_screenheight() // 2) - (200 // 2)
    root.geometry(f"500x200+{x}+{y}")
    
    # Progress elements
    status_label = tk.Label(root, text="Connecting to SFTP server...", font=("Arial", 10))
    status_label.pack(pady=20)
    
    progress_var = tk.StringVar()
    progress_label = tk.Label(root, textvariable=progress_var, font=("Arial", 9))
    progress_label.pack(pady=10)
    
    progress_bar = ttk.Progressbar(root, mode='indeterminate')
    progress_bar.pack(pady=10, padx=50, fill=tk.X)
    progress_bar.start()
    
    # Log text area
    log_frame = tk.Frame(root)
    log_frame.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)
    
    log_text = tk.Text(log_frame, height=6, font=("Consolas", 8))
    scrollbar = tk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
    log_text.configure(yscrollcommand=scrollbar.set)
    
    log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def update_status(text):
        status_label.config(text=text)
        root.update()
    
    def update_progress(text):
        progress_var.set(text)
        log_text.insert(tk.END, text + "\n")
        log_text.see(tk.END)
        root.update()
    
    def finish_upload(success=True):
        progress_bar.stop()
        if success:
            status_label.config(text="Upload completed successfully!")
            messagebox.showinfo("Upload Complete", "Files uploaded successfully to SFTP server!")
        else:
            status_label.config(text="Upload failed!")
            messagebox.showerror("Upload Failed", "An error occurred during upload. Check the log for details.")
        root.after(2000, root.destroy)  # Close window after 2 seconds
    
    root.update()
    return root, update_status, update_progress, finish_upload

def get_user_selection_gui():
    """
    Immediately opens a native Windows Explorer dialog:
    - First: file picker (allows multi-select). If user cancels, then
    - Second: folder picker.
    Returns: list of files OR a single folder path string OR None.
    Falls back to CLI if GUI is unavailable.
    """
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.update()

        # 1) Let user pick one or more files. If they cancel, offer folder picker.
        file_paths = filedialog.askopenfilenames(
            title="Select file(s) to upload (Cancel to pick a folder)",
            filetypes=[("All files", "*.*")]
        )
        if file_paths:
            root.destroy()
            return list(file_paths)

        # 2) Folder picker if no files selected
        folder_path = filedialog.askdirectory(title="Select a folder to upload")
        root.destroy()
        return folder_path if folder_path else None

    except Exception as e:
        print(f"GUI failed to start: {e}")
        try:
            root.destroy()
        except Exception:
            pass
        print("Falling back to command line mode...")
        return get_user_selection_cli()

def get_user_selection_cli():
    """
    Command line fallback for file/folder selection.
    """
    print("\n" + "="*50)
    print("SFTP UPLOADER - COMMAND LINE MODE")
    print("="*50)
    
    while True:
        print("\nOptions:")
        print("1. Enter file path")
        print("2. Enter folder path")
        print("3. List current directory")
        print("4. Exit")
        
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == '1':
            file_path = input("Enter full path to file: ").strip().strip('"')
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return file_path
            else:
                print("File does not exist or is not a file. Please try again.")
        
        elif choice == '2':
            folder_path = input("Enter full path to folder: ").strip().strip('"')
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                return folder_path
            else:
                print("Folder does not exist or is not a directory. Please try again.")
        
        elif choice == '3':
            current_dir = os.getcwd()
            print(f"\nCurrent directory: {current_dir}")
            print("\nContents:")
            try:
                for i, item in enumerate(os.listdir(current_dir), 1):
                    item_path = os.path.join(current_dir, item)
                    item_type = "DIR " if os.path.isdir(item_path) else "FILE"
                    print(f"{i:2d}. [{item_type}] {item}")
                
                selection = input("\nEnter number to select item (or press Enter to continue): ").strip()
                if selection.isdigit():
                    idx = int(selection) - 1
                    items = os.listdir(current_dir)
                    if 0 <= idx < len(items):
                        selected_item = os.path.join(current_dir, items[idx])
                        return selected_item
            except Exception as e:
                print(f"Error listing directory: {e}")
        
        elif choice == '4':
            return None
        
        else:
            print("Invalid option. Please try again.")

def main():
    print("SFTP Uploader Script - Starting...")
    
    # SFTP server details
    hostname = ""
    port = 2022
    username = ""
    password = ""
    # Remote base directory on the SFTP server. By default use the SFTP start directory.
    # Override by setting the env var SFTP_REMOTE_BASE (e.g., "/some/subdir").
    remote_base_path = os.getenv("SFTP_REMOTE_BASE", "")
    
    # Get user selection
    if len(sys.argv) > 1:
        # Use command line argument if provided
        arg_path = sys.argv[1]
        if not os.path.exists(arg_path):
            print(f"Error: Path '{arg_path}' does not exist.")
            return
        selection = arg_path
    else:
        # Try GUI first, fall back to CLI if needed
        try:
            print("Attempting to start GUI...")
            selection = get_user_selection_gui()
        except Exception as e:
            print(f"GUI failed: {e}")
            print("Using command line mode...")
            selection = get_user_selection_cli()
        
        if not selection:
            print("No file or folder selected. Exiting.")
            return

    # Normalize selection for downstream logic
    is_multi_files = isinstance(selection, list)
    if is_multi_files and len(selection) == 1:
        # Collapse single-item list
        selection = selection[0]
        is_multi_files = False

    # Prepare confirmation text
    if is_multi_files:
        preview = os.path.commonpath(selection)
        file_type = f"{len(selection)} file(s)"
        display_name = preview
    else:
        display_name = selection
        file_type = "folder" if os.path.isdir(selection) else "file"

    print(f"\nSelected: {display_name}")
    confirm = input(f"\nUpload {file_type} to SFTP server? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Upload cancelled.")
        return
    
    print(f"\nConnecting to {hostname}:{port}...")
    
    try:
        # Connect to the SFTP server
        print("Connecting to SFTP server...")
        
        transport = paramiko.Transport((hostname, port))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        
        print("Connected successfully!")
        # Ensure remote base exists only if set to a non-root path
        if remote_base_path and remote_base_path != "/":
            create_remote_directory_recursive(sftp, remote_base_path)
        print("Starting upload...")
        
        # Upload the selected path(s) with progress
        def progress_callback(message):
            print(f"  {message}")

        if is_multi_files:
            # Preserve structure from their common parent
            base_dir = os.path.commonpath(selection)
            upload_files_list(selection, sftp, remote_base_path, progress_callback, base_dir)
        else:
            upload_to_sftp(selection, sftp, remote_base_path, progress_callback)
        
        print("\n" + "="*50)
        print("Upload completed successfully!")
        
    except Exception as e:
        error_msg = f"An error occurred: {e}"
        print(error_msg)
    finally:
        try:
            sftp.close()
            transport.close()
            print("Connection closed.")
        except:
            pass

if __name__ == "__main__":
    main()
