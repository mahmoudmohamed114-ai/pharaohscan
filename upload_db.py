import os
import re
import json
from bson import json_util
import pymongo

def get_mongo_uri():
    # Search for atlas-credentials.env in current or parent directories
    paths = [
        "atlas-credentials.env",
        "../atlas-credentials.env",
        os.path.join(os.path.dirname(__file__), "atlas-credentials.env"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "atlas-credentials.env"))
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    for line in f:
                        match = re.match(r'^\s*MONGODB_URI\s*=\s*["\']?(.*?)["\']?\s*$', line)
                        if match:
                            uri = match.group(1).strip()
                            print(f"[INFO] Loaded MongoDB Atlas URI from: {p}")
                            return uri
            except Exception as e:
                print(f"[WARNING] Error reading {p}: {e}")
                
    # Fallback to local
    print("[WARNING] Could not find atlas-credentials.env. Falling back to localhost.")
    return "mongodb://127.0.0.1:27017/heritage_social"

def find_database_dir():
    paths = [
        "Database",
        "../Database",
        os.path.join(os.path.dirname(__file__), "Database"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Database"))
    ]
    for p in paths:
        if os.path.exists(p) and os.path.isdir(p):
            print(f"[INFO] Found Database directory at: {p}")
            return p
    raise FileNotFoundError("Could not locate Database/ directory containing seed files.")

def main():
    print("===================================================")
    print("MongoDB Atlas Seeder & Database Uploader")
    print("===================================================")
    
    # 1. Connect to MongoDB Atlas
    uri = get_mongo_uri()
    db_name = "heritage_social"
    
    # Check if database name is appended in URI, parse if needed
    print("[INFO] Connecting to MongoDB Atlas cluster...")
    client = pymongo.MongoClient(uri)
    db = client[db_name]
    
    # Run a quick ping to verify connection
    try:
        client.admin.command('ping')
        print("[SUCCESS] Connected to MongoDB successfully!")
    except Exception as e:
        print(f"[ERROR] Failed to connect to MongoDB: {e}")
        return
        
    # 2. Locate Database directory
    try:
        db_dir = find_database_dir()
    except Exception as e:
        print(f"[ERROR] {e}")
        return
        
    # 3. Seed Collections
    files_mapping = {
        "objects": "heritage_social.objects.json",
        "posts": "heritage_social.posts.json",
        "training_candidates": "heritage_social.training_candidates.json"
    }
    
    for collection_name, filename in files_mapping.items():
        file_path = os.path.join(db_dir, filename)
        if not os.path.exists(file_path):
            print(f"[WARNING] File not found: {file_path}. Skipping collection '{collection_name}'...")
            continue
            
        print(f"\n-- Seeding Collection: '{collection_name}' --")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json_util.loads(f.read())
                
            # Clear existing data
            delete_res = db[collection_name].delete_many({})
            print(f"  Cleared {delete_res.deleted_count} old documents.")
            
            # Insert new data
            if data:
                insert_res = db[collection_name].insert_many(data)
                print(f"  Inserted {len(insert_res.inserted_ids)} documents.")
            else:
                print("  No documents found in JSON file to insert.")
                
        except Exception as e:
            print(f"[ERROR] Failed to seed '{collection_name}': {e}")
            
    # 4. Seed Default Locations (L001 and L002)
    print("\n-- Seeding Collection: 'locations' --")
    default_locations = [
        {
            "location_id": "L001",
            "name": "Giza Pyramids",
            "latitude": 29.9792,
            "longitude": 31.1342,
            "geohash": "stq4s3"
        },
        {
            "location_id": "L002",
            "name": "Egyptian Museum",
            "latitude": 30.0478,
            "longitude": 31.2336,
            "geohash": "stq4yw"
        }
    ]
    
    try:
        # Clear existing locations
        delete_loc = db["locations"].delete_many({})
        print(f"  Cleared {delete_loc.deleted_count} old location documents.")
        
        # Insert
        insert_loc = db["locations"].insert_many(default_locations)
        print(f"  Inserted {len(insert_loc.inserted_ids)} default location records.")
        
        # Create Indexes
        print("\n-- Creating Indexes --")
        db["locations"].create_index("geohash")
        db["locations"].create_index("location_id", unique=True)
        db["objects"].create_index("geohash")
        db["objects"].create_index("location_id")
        db["objects"].create_index("object_id", unique=True)
        db["posts"].create_index("object_id")
        db["posts"].create_index("location_id")
        db["posts"].create_index("post_id", unique=True)
        db["training_candidates"].create_index("status")
        db["training_candidates"].create_index("createdAt")
        print("  Created geo and unique indexes on locations, objects, posts, and candidates.")
        
    except Exception as e:
        print(f"[ERROR] Failed to seed locations / indexes: {e}")
        
    print("\n===================================================")
    print("Database seeding completed.")
    print("===================================================\n")

if __name__ == "__main__":
    main()
