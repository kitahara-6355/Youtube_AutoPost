import os
import json
from google.cloud import firestore
from google.cloud import videointelligence_v1 as videointelligence
from google.cloud.video import transcoder_v1
from google.cloud import storage
from google.protobuf.duration_pb2 import Duration

# --- Environment Variables ---
PROJECT_ID = os.environ.get("GCP_PROJECT")
LOCATION = os.environ.get("GCP_REGION")
VIDEO_COLLECTION = "videos"

# --- Initialize Clients ---
db = firestore.Client()
video_intelligence_client = videointelligence.VideoIntelligenceServiceClient()
transcoder_client = transcoder_v1.TranscoderServiceClient()
storage_client = storage.Client()

def trigger_analysis(event, context):
    """
    Cloud Function to be triggered by a video upload to GCS.
    This function starts the video analysis process.
    """
    file_name = event["name"]
    bucket_name = event["bucket"]

    # Ignore files in subdirectories to prevent infinite loops
    if "/" in file_name:
        print(f"Ignoring file '{file_name}' in subdirectory.")
        return

    print(f"Processing new video: {file_name}")

    # 1. Create a document in Firestore for the new video
    doc_ref = db.collection(VIDEO_COLLECTION).document(file_name)
    doc_ref.set({
        "filename": file_name,
        "gcs_path": f"gs://{bucket_name}/{file_name}",
        "uploaded_at": firestore.SERVER_TIMESTAMP,
        "analysis_status": "PROCESSING",
        "edit_status": "PENDING",
        "downloaded_by_main": False,
        "downloaded_by_sub": False,
        "deleted_from_gcs": False,
    })

    # 2. Start the Vertex AI analysis job
    gcs_uri = f"gs://{bucket_name}/{file_name}"
    analysis_output_uri = f"gs://{bucket_name}/analysis_results/{os.path.splitext(file_name)[0]}.json"

    try:
        video_intelligence_client.annotate_video(
            request={
                "features": [videointelligence.Feature.SCENE_DETECTION],
                "input_uri": gcs_uri,
                "output_uri": analysis_output_uri,
                "location_id": LOCATION,
            }
        )
        print(f"Analysis job started for {file_name}.")
    except Exception as e:
        print(f"Error starting analysis job: {e}")
        doc_ref.update({"analysis_status": "FAILED"})


def trigger_editing(event, context):
    """
    Cloud Function triggered by the creation of an analysis JSON file.
    This function starts the video editing process.
    """
    json_file_name = event["name"]
    bucket_name = event["bucket"]

    # Ensure we only process files in the analysis_results folder
    if not json_file_name.startswith("analysis_results/"):
        print(f"Ignoring file '{json_file_name}' not in analysis_results/ folder.")
        return

    print(f"Processing analysis result: {json_file_name}")

    # Derive original filename from the JSON filename
    original_filename = os.path.splitext(os.path.basename(json_file_name))[0] + ".mp4" # Assuming .mp4, might need to be more robust
    doc_ref = db.collection(VIDEO_COLLECTION).document(original_filename)

    # 1. Update Firestore with analysis completion
    gcs_json_path = f"gs://{bucket_name}/{json_file_name}"
    doc_ref.update({
        "analysis_status": "COMPLETE",
        "analysis_json_path": gcs_json_path
    })

    # 2. Get scene times from the JSON file
    bucket = storage_client.bucket(bucket_name)
    json_blob = bucket.get_blob(json_file_name)
    if not json_blob:
        print(f"Error: Could not find JSON file: {json_file_name} in bucket {bucket_name}")
        doc_ref.update({"edit_status": "FAILED", "error_message": "Analysis JSON file not found."})
        return

    json_data = json.loads(json_blob.download_as_string())
    shots = json_data.get("annotation_results", [{}])[0].get("shot_annotations", [])
    scene_times = []
    for shot in shots:
        start_time = shot.get("start_time_offset", {})
        end_time = shot.get("end_time_offset", {})
        if "seconds" in start_time and "seconds" in end_time:
            scene_times.append({
                "start": float(start_time.get("seconds", 0)) + float(start_time.get("nanos", 0)) / 1e9,
                "end": float(end_time.get("seconds", 0)) + float(end_time.get("nanos", 0)) / 1e9,
            })

    if not scene_times:
        print("No scenes found in analysis file. Skipping edit.")
        doc_ref.update({"edit_status": "SKIPPED"})
        return

    # 3. Start the Transcoder API job
    original_video_uri = f"gs://{bucket_name}/{original_filename}"
    edited_video_filename = "EDITED_" + original_filename
    edited_video_gcs_path = f"gs://{bucket_name}/edited_videos/"

    edit_list = []
    for i, scene in enumerate(scene_times):
        atom = transcoder_v1.types.EditAtom()
        atom.key = f"scene-{i}"
        atom.inputs = ["input0"]
        atom.start_time_offset = Duration(seconds=int(scene["start"]))
        duration = min(2.0, scene["end"] - scene["start"])
        atom.end_time_offset = Duration(seconds=int(scene["start"] + duration), nanos=int((scene["start"] + duration)%1 * 1e9))
        edit_list.append(atom)

    job_config = transcoder_v1.types.JobConfig(
        edit_list=edit_list,
        elementary_streams=[
            transcoder_v1.types.ElementaryStream(
                key="video-stream",
                video_stream=transcoder_v1.types.VideoStream(
                    h264=transcoder_v1.types.VideoStream.H264CodecSettings(
                        height_pixels=720,
                        width_pixels=1280,
                        bitrate_bps=2500000,
                        frame_rate=30,
                    )
                ),
            ),
            transcoder_v1.types.ElementaryStream(
                key="audio-stream",
                audio_stream=transcoder_v1.types.AudioStream(codec="aac", bitrate_bps=64000),
            ),
        ],
        mux_streams=[
            transcoder_v1.types.MuxStream(
                key=edited_video_filename,
                container="mp4",
                elementary_streams=["video-stream", "audio-stream"],
            ),
        ],
    )

    try:
        parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
        job = transcoder_v1.types.Job(
            input_uri=original_video_uri,
            output_uri=edited_video_gcs_path,
            config=job_config,
        )

        transcoder_client.create_job(parent=parent, job=job)
        print(f"Transcoder job created for {original_filename}.")
        doc_ref.update({
            "edit_status": "PROCESSING",
            "edited_video_path": edited_video_gcs_path + edited_video_filename
        })
    except Exception as e:
        print(f"Error starting transcoder job: {e}")
        doc_ref.update({"edit_status": "FAILED"})
