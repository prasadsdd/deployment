from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import os
import json
import hashlib
import time
import webbrowser
import threading
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from rag_processor import RAGProcessor
import uuid
import traceback

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this-in-production'

# Configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB (reduced for stability)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Global RAG processor - will be initialized when needed
rag_processor = None

def get_rag_processor():
    """Lazy initialization of RAG processor with error handling"""
    global rag_processor
    if rag_processor is None:
        try:
            print("Initializing RAG processor...")
            rag_processor = RAGProcessor()
            print("RAG processor initialized successfully!")
        except Exception as e:
            print(f"Failed to initialize RAG processor: {str(e)}")
            traceback.print_exc()
            raise e
    return rag_processor

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_pdf_hash(file_path):
    """Generate a hash for the PDF file"""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except Exception as e:
        print(f"Error generating PDF hash: {e}")
        raise e

def open_browser():
    """Open browser after a short delay"""
    time.sleep(2)
    try:
        webbrowser.open('http://127.0.0.1:5000')
    except Exception as e:
        print(f"Could not open browser: {e}")

def cleanup_old_files():
    """Clean up old uploaded files"""
    try:
        if 'pdf_path' in session and os.path.exists(session['pdf_path']):
            os.remove(session['pdf_path'])
            print(f"Removed old PDF: {session['pdf_path']}")
    except Exception as e:
        print(f"Could not remove old PDF: {e}")

# Enhanced error handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    print("413 Error: File too large")
    return jsonify({
        'error': 'File is too large. Please upload a PDF file smaller than 50MB.',
        'success': False
    }), 413

@app.errorhandler(500)
def internal_server_error(error):
    print(f"500 Error: {str(error)}")
    return jsonify({
        'error': 'Internal server error occurred. Please try again in a few minutes.',
        'success': False
    }), 500

@app.errorhandler(503)
def service_unavailable(error):
    print(f"503 Error: Service unavailable - {str(error)}")
    return jsonify({
        'error': 'Service temporarily unavailable. Please try again in a few minutes.',
        'success': False,
        'retry_suggested': True
    }), 503

@app.route('/')
def index():
    """Landing page"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Enhanced upload with comprehensive error handling"""
    try:
        print("=== UPLOAD REQUEST STARTED ===")
        print(f"Request content length: {request.content_length}")
        print(f"Max content length: {app.config.get('MAX_CONTENT_LENGTH')}")
        
        # Validate request
        if 'file' not in request.files:
            print("ERROR: No file in request")
            return jsonify({'error': 'No file selected', 'success': False}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            print("ERROR: Empty filename")
            return jsonify({'error': 'No file selected', 'success': False}), 400
        
        if not allowed_file(file.filename):
            print(f"ERROR: Invalid file type: {file.filename}")
            return jsonify({'error': 'Invalid file type. Please upload a PDF file.', 'success': False}), 400
        
        print(f"Processing file: {file.filename} (Size: {request.content_length} bytes)")
        
        # Clean up previous session
        cleanup_old_files()
        session.clear()
        
        # Clear RAG processor cache if it exists
        global rag_processor
        if rag_processor and hasattr(rag_processor, 'vectorstores'):
            rag_processor.vectorstores.clear()
            print("Cleared RAG processor cache")
        
        # Save the uploaded file
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        print(f"Saving file to: {file_path}")
        
        try:
            file.save(file_path)
        except Exception as save_error:
            print(f"Error saving file: {save_error}")
            return jsonify({'error': f'Failed to save file: {str(save_error)}', 'success': False}), 500
        
        # Verify file was saved
        if not os.path.exists(file_path):
            return jsonify({'error': 'File was not saved successfully', 'success': False}), 500
        
        # Generate PDF hash
        try:
            pdf_hash = get_pdf_hash(file_path)
            print(f"Generated PDF hash: {pdf_hash}")
        except Exception as hash_error:
            os.remove(file_path)  # Clean up
            return jsonify({'error': f'Failed to process PDF: {str(hash_error)}', 'success': False}), 500
        
        # Set session data
        session['pdf_path'] = file_path
        session['pdf_name'] = filename
        session['pdf_hash'] = pdf_hash
        session['chat_history'] = []
        session['is_processed'] = False
        
        print("=== UPLOAD COMPLETED SUCCESSFULLY ===")
        return jsonify({
            'success': True,
            'pdf_hash': pdf_hash,
            'pdf_name': filename,
            'message': 'File uploaded successfully'
        })
        
    except RequestEntityTooLarge:
        print("ERROR: File too large (RequestEntityTooLarge)")
        return jsonify({'error': 'File is too large. Please use a PDF file smaller than 50MB.', 'success': False}), 413
    
    except Exception as e:
        print(f"UPLOAD ERROR: {str(e)}")
        traceback.print_exc()
        
        # Clean up any partially created files
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        return jsonify({'error': f'Upload failed: {str(e)}', 'success': False}), 500

@app.route('/process-pdf', methods=['POST'])
def process_pdf():
    """Process PDF and create embeddings with enhanced error handling"""
    if 'pdf_path' not in session:
        return jsonify({'error': 'No PDF uploaded', 'success': False}), 400
    
    try:
        print("=== PDF PROCESSING STARTED ===")
        
        # Initialize RAG processor
        try:
            processor = get_rag_processor()
        except Exception as init_error:
            print(f"Failed to initialize RAG processor: {init_error}")
            return jsonify({
                'error': 'Failed to initialize AI processor. Please try again in a few minutes.',
                'success': False
            }), 503
        
        pdf_path = session['pdf_path']
        pdf_hash = session['pdf_hash']
        
        print(f"Processing PDF: {pdf_path}")
        print(f"PDF Hash: {pdf_hash}")
        
        # Verify file still exists
        if not os.path.exists(pdf_path):
            return jsonify({
                'error': 'PDF file not found. Please re-upload your document.',
                'success': False
            }), 404
        
        # Process the PDF
        result = processor.process_pdf(pdf_path, pdf_hash)
        
        if result['success']:
            session['is_processed'] = True
            
            # Check if it was existing or newly processed
            is_existing = result.get('is_existing', False)
            
            response_data = {
                'success': True,
                'is_existing': is_existing
            }
            
            if is_existing:
                response_data['message'] = 'PDF already processed. Loading existing embeddings...'
            else:
                chunk_count = result.get('chunk_count', 0)
                response_data['message'] = f"PDF processed successfully! Created {chunk_count} document chunks."
                response_data['chunk_count'] = chunk_count
            
            print("=== PDF PROCESSING COMPLETED SUCCESSFULLY ===")
            return jsonify(response_data)
            
        else:
            error_message = result.get('error', 'Unknown processing error')
            print(f"Processing failed: {error_message}")
            
            # Check if it's a service-related error
            if any(keyword in error_message.lower() for keyword in ['pinecone', 'network', 'timeout', 'connection', 'internal server']):
                return jsonify({
                    'error': 'AI service is temporarily experiencing issues. Please try again in a few minutes.',
                    'success': False,
                    'retry_suggested': True
                }), 503
            else:
                return jsonify({
                    'error': f'Processing failed: {error_message}',
                    'success': False
                }), 500
            
    except Exception as e:
        print(f"PROCESSING ERROR: {str(e)}")
        traceback.print_exc()
        
        # Check if it's likely a service issue
        if any(keyword in str(e).lower() for keyword in ['pinecone', 'network', 'timeout', 'connection']):
            return jsonify({
                'error': 'AI service is temporarily experiencing issues. Please try again in a few minutes.',
                'success': False,
                'retry_suggested': True
            }), 503
        else:
            return jsonify({
                'error': f'Processing failed: {str(e)}',
                'success': False
            }), 500

@app.route('/chat')
def chat():
    """Chat interface"""
    if 'pdf_path' not in session or not session.get('is_processed', False):
        return redirect(url_for('index'))
    
    return render_template('chat.html', 
                         pdf_name=session['pdf_name'],
                         pdf_hash=session['pdf_hash'])

@app.route('/ask', methods=['POST'])
def ask_question():
    """Handle question asking with enhanced error handling"""
    if 'pdf_hash' not in session or not session.get('is_processed', False):
        return jsonify({'error': 'No PDF processed', 'success': False}), 400
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request data', 'success': False}), 400
        
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({'error': 'Please enter a question', 'success': False}), 400
        
        print(f"Processing question: {question[:100]}...")
        start_time = time.time()
        
        try:
            processor = get_rag_processor()
        except Exception as init_error:
            return jsonify({
                'error': 'AI service temporarily unavailable. Please try again.',
                'success': False
            }), 503
        
        pdf_hash = session['pdf_hash']
        result = processor.get_answer(pdf_hash, question)
        
        response_time = time.time() - start_time
        
        if result['success']:
            # Store in chat history
            chat_entry = {
                'question': question,
                'answer': result['answer'],
                'response_time': round(response_time, 2),
                'sources': result.get('sources', []),
                'timestamp': time.time()
            }
            
            if 'chat_history' not in session:
                session['chat_history'] = []
            
            session['chat_history'].append(chat_entry)
            session.modified = True
            
            return jsonify({
                'success': True,
                'answer': result['answer'],
                'response_time': round(response_time, 2),
                'sources': result.get('sources', [])
            })
        else:
            print(f"Question processing failed: {result.get('error')}")
            return jsonify({
                'error': result.get('error', 'Failed to process question'),
                'success': False
            }), 500
            
    except Exception as e:
        print(f"Question processing error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'error': 'Failed to process question. Please try again.',
            'success': False
        }), 500

@app.route('/get-chat-history')
def get_chat_history():
    """Get chat history"""
    return jsonify({
        'chat_history': session.get('chat_history', [])
    })

@app.route('/view-pdf')
def view_pdf():
    """View uploaded PDF"""
    if 'pdf_path' not in session:
        return "PDF not found", 404
    
    pdf_path = session['pdf_path']
    if not os.path.exists(pdf_path):
        return "PDF file not found", 404
    
    return send_file(pdf_path, mimetype='application/pdf')

@app.route('/clear-chat', methods=['POST'])
def clear_chat():
    """Clear chat history"""
    session['chat_history'] = []
    session.modified = True
    return jsonify({'success': True})

@app.route('/reset', methods=['POST'])
def reset_session():
    """Enhanced session reset with comprehensive cleanup"""
    try:
        print("=== RESET REQUEST STARTED ===")
        
        # Clean up uploaded files
        cleanup_old_files()
        
        # Clear session data
        old_hash = session.get('pdf_hash', 'unknown')
        session.clear()
        print(f"Cleared session for PDF hash: {old_hash}")
        
        # Clear RAG processor cache
        global rag_processor
        if rag_processor and hasattr(rag_processor, 'vectorstores'):
            rag_processor.vectorstores.clear()
            print("Cleared RAG processor cache")
        
        print("=== RESET COMPLETED SUCCESSFULLY ===")
        return jsonify({
            'success': True,
            'message': 'Session cleared successfully'
        })
        
    except Exception as e:
        print(f"Reset error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'error': f'Reset failed: {str(e)}',
            'success': False
        }), 500

if __name__ == '__main__':
    print("Starting PashAI Flask application...")
    print("RAG processor will be initialized when first needed.")
    
    # Only open browser if NOT in reloader process
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print("Opening browser automatically...")
        threading.Thread(target=open_browser, daemon=True).start()
    else:
        print("Reloader process - skipping browser opening")
    
    # IMPORTANT: Disable debug mode to prevent app restarts during processing
    app.run(debug=False, port=5000, host='127.0.0.1', threaded=True)

