import streamlit as st
from PIL import Image
import io
import time

# --- Page Configuration ---
st.set_page_config(page_title="Image Tool Suite", page_icon="", layout="wide")

st.title("All-in-One Image Toolkit")
st.markdown("Use the tabs below to Convert, Compress, Resize, or Edit Backgrounds.")

# --- CSS Styling ---
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
def convert_to_bytes(img, format="JPEG", quality=100):
    buf = io.BytesIO()
    img.save(buf, format=format, quality=quality)
    byte_im = buf.getvalue()
    return byte_im

def format_size(size):
    # Convert bytes to KB or MB
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'KB', 2: 'MB', 3: 'GB'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

# --- Tabs Setup ---
tab1, tab2, tab3, tab4 = st.tabs([
    "Converter (to JPEG)", 
    "Compressor", 
    "Resizer", 
    "Background Tool"
])

# ==========================
# TAB 1: CONVERTER (To JPEG)
# ==========================
with tab1:
    st.header("Convert Images to JPEG")
    uploaded_files_conv = st.file_uploader("Upload images (PNG, WEBP, BMP...)", type=['png', 'webp', 'bmp', 'tiff'], accept_multiple_files=True, key="conv_uploader")
    
    if uploaded_files_conv:
        st.write(f"Processing {len(uploaded_files_conv)} images...")
        
        for uploaded_file in uploaded_files_conv:
            with st.expander(f"File: {uploaded_file.name}", expanded=True):
                # Open Image
                image = Image.open(uploaded_file)

                # Convert Logic
                if image.mode in ("RGBA", "P"):
                    image = image.convert("RGB")
                
                converted_bytes = convert_to_bytes(image, format="JPEG")
                
                st.download_button(
                    label=f"⬇️ Download {uploaded_file.name.split('.')[0]}.jpg",
                    data=converted_bytes,
                    file_name=f"{uploaded_file.name.split('.')[0]}.jpg",
                    mime="image/jpeg"
                )

# ==========================
# TAB 2: COMPRESSOR
# ==========================
with tab2:
    st.header("Compress Images")
    
    # Settings
    quality_val = st.slider("Compression Quality (Lower = Smaller File)", min_value=1, max_value=95, value=50, step=5)
    uploaded_files_comp = st.file_uploader("Upload images to compress", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key="comp_uploader")
    
    if uploaded_files_comp:
        # Progress Bar
        progress_bar = st.progress(0)
        total_files = len(uploaded_files_comp)
        
        for i, uploaded_file in enumerate(uploaded_files_comp):
            image = Image.open(uploaded_file)
            
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            
            # Compress
            compressed_bytes = convert_to_bytes(image, format="JPEG", quality=quality_val)
            
            # Calculate stats
            original_size = uploaded_file.size
            compressed_size = len(compressed_bytes)
            saved_percent = 100 - (compressed_size / original_size * 100)
            
            # Display Result
            with st.container():
                st.markdown("---")
                cols = st.columns([1, 2, 1])
                with cols[0]:
                    st.image(image, width=100)
                with cols[1]:
                    st.write(f"**{uploaded_file.name}**")
                    st.write(f"Original: `{format_size(original_size)}` → Compressed: `{format_size(compressed_size)}`")
                    if saved_percent > 0:
                        st.success(f"Saved {saved_percent:.1f}% space!")
                    else:
                        st.warning("File size increased (try lower quality).")
                with cols[2]:
                    st.download_button(
                        label="⬇️ Download",
                        data=compressed_bytes,
                        file_name=f"compressed_{uploaded_file.name.split('.')[0]}.jpg",
                        mime="image/jpeg"
                    )
            
            # Update Progress
            progress_bar.progress((i + 1) / total_files)
            time.sleep(0.1)

# ==========================
# TAB 3: RESIZER (WITH PREVIEW)
# ==========================
with tab3:
    st.header("Resize Image Dimensions")
    uploaded_file_resize = st.file_uploader("Upload an image", type=['png', 'jpg', 'jpeg'], key="resize_uploader")
    
    if uploaded_file_resize:
        image = Image.open(uploaded_file_resize)
        
        # --- PREVIEW SECTION ---
        st.markdown("#### Preview (Original)")
        # Shows the image immediately
        st.image(image, caption=f"Original Size: {image.width} x {image.height} px", use_container_width=True)
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            new_width = st.number_input("New Width", value=image.width)
        with col2:
            new_height = st.number_input("New Height", value=image.height)
            
        maintain_aspect = st.checkbox("Maintain Aspect Ratio (Calculates Height auto)", value=True)
        
        if maintain_aspect:
             aspect_ratio = image.height / image.width
             new_height = int(new_width * aspect_ratio)
             st.info(f"Height adjusted to {new_height}px to maintain aspect ratio.")

        if st.button("Apply Resize"):
            resized_image = image.resize((int(new_width), int(new_height)))
            
            st.success("Image Resized!")
            st.image(resized_image, caption=f"Resized to {new_width}x{new_height}", use_container_width=True)
            
            buf = io.BytesIO()
            resized_image.save(buf, format="PNG")
            byte_im = buf.getvalue()
            
            st.download_button(
                label="⬇️ Download Resized Image",
                data=byte_im,
                file_name=f"resized_{uploaded_file_resize.name}",
                mime="image/png"
            )

# ==========================
# TAB 4: BACKGROUND TOOL (WITH PREVIEW)
# ==========================
with tab4:
    st.header("Remove & Replace Background")
    uploaded_file_bg = st.file_uploader("Upload image (Person/Object)", type=['png', 'jpg', 'jpeg'], key="bg_uploader")
    
    if uploaded_file_bg:
        # Create two columns: Controls on Left, Preview on Right
        col_ctrl, col_prev = st.columns([1, 2])
        
        # --- CONTROL COLUMN ---
        with col_ctrl:
            st.markdown("### Settings")
            bg_color = st.color_picker("Pick Background Color", "#ffffff")
            process_btn = st.button("Process Background")
        
        # --- PREVIEW COLUMN ---
        with col_prev:
            # If button NOT clicked yet, show Original
            if not process_btn:
                st.markdown("### Original Preview")
                st.image(uploaded_file_bg, caption="Original Image", use_container_width=True)
            
            # If button CLICKED, show Processing/Result
            else:
                with st.spinner("Removing background (this may take a moment)..."):
                    from rembg import remove
                    input_image = Image.open(uploaded_file_bg)
                    
                    # 1. Remove Background
                    no_bg_image = remove(input_image)
                    
                    # 2. Create Solid Color Background
                    new_bg = Image.new("RGBA", no_bg_image.size, bg_color)
                    
                    # 3. Paste foreground
                    new_bg.paste(no_bg_image, (0, 0), no_bg_image)
                    
                    # Show Result
                    st.markdown("### Result")
                    st.image(new_bg, caption="New Background Applied", use_container_width=True)
                    
                    # Prepare Download
                    buf = io.BytesIO()
                    new_bg.convert("RGB").save(buf, format="JPEG")
                    byte_im = buf.getvalue()
                    
                    st.download_button(
                        label="⬇️ Download Image",
                        data=byte_im,
                        file_name="new_background.jpg",
                        mime="image/jpeg"
                    )
