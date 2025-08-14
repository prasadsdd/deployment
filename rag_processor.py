import os
import json
import hashlib
import time
import random
import uuid  # ← ADD THIS LINE
from dotenv import load_dotenv
from langchain_docling import DoclingLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_docling.loader import ExportType
from langchain_pinecone import PineconeVectorStore
from langchain_aws import BedrockEmbeddings, ChatBedrock
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from pinecone import Pinecone, ServerlessSpec
import traceback


# Load environment variables.
load_dotenv()

class RAGProcessor:
    def __init__(self):
        print("Initializing BedrockEmbeddings...")
        self.embeddings = BedrockEmbeddings(
            model_id="amazon.titan-embed-text-v2:0",
            region_name="us-east-1",
            model_kwargs={"dimensions": 1024, "normalize": True}
        )
        
        print("Initializing Pinecone...")
        self.pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
        
        print("Initializing ChatBedrock...")
        self.llm = ChatBedrock(
            model_id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            region_name="us-east-1"
        )
        
        print("RAG processor initialized successfully!")
        self.vectorstores = {}
    
    def is_pdf_processed(self, pdf_hash):
        """Check if PDF is already processed with better error handling"""
        try:
            # Look for any index that starts with pdf-{hash}
            all_indexes = self.pc.list_indexes()
            for index_info in all_indexes:
                if index_info['name'].startswith(f"pdf-{pdf_hash}"):
                    # Test if the index is accessible and has data
                    try:
                        index = self.pc.Index(index_info['name'])
                        stats = index.describe_index_stats()
                        if stats['total_vector_count'] > 0:
                            return True
                    except Exception as e:
                        print(f"Error accessing index {index_info['name']}: {e}")
                        continue
            return False
        except Exception as e:
            print(f"Error checking if PDF processed: {e}")
            return False
    
    def cleanup_existing_index(self, index_name):
        """Clean up existing index to avoid conflicts"""
        try:
            if self.pc.has_index(index_name):
                print(f"Index {index_name} already exists, deleting...")
                self.pc.delete_index(index_name)
                
                # Wait for deletion to complete with timeout
                max_wait = 90  # 1.5 minutes
                wait_time = 0
                while wait_time < max_wait:
                    if not self.pc.has_index(index_name):
                        print(f"Index {index_name} deleted successfully")
                        return True
                    time.sleep(5)
                    wait_time += 5
                    print(f"Waiting for index deletion... ({wait_time}s)")
                
                print(f"Warning: Index {index_name} still exists after {max_wait}s")
                return False
        except Exception as e:
            print(f"Error cleaning up existing index: {e}")
            return False
    
    def process_pdf_with_exponential_backoff(self, pdf_path, pdf_hash):
        """Process PDF with exponential backoff retry strategy"""
        max_attempts = 5
        base_delay = 2
        
        for attempt in range(max_attempts):
            try:
                print(f"=== PROCESSING ATTEMPT {attempt + 1}/{max_attempts} ===")
                result = self._process_pdf_single_attempt(pdf_path, pdf_hash)
                
                if result['success']:
                    return result
                else:
                    if attempt == max_attempts - 1:
                        return result  # Return the last error
                    
                    # Calculate delay with exponential backoff + jitter
                    delay = (base_delay * (2 ** attempt)) + random.uniform(0, 2)
                    print(f"Attempt {attempt + 1} failed: {result.get('error', 'Unknown error')}")
                    print(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                    
            except Exception as e:
                if attempt == max_attempts - 1:
                    return {
                        'success': False,
                        'error': f'Failed after {max_attempts} attempts. Last error: {str(e)}'
                    }
                
                delay = (base_delay * (2 ** attempt)) + random.uniform(0, 2)
                print(f"Attempt {attempt + 1} exception: {str(e)}")
                print(f"Retrying in {delay:.1f} seconds...")
                time.sleep(delay)
        
        return {
            'success': False,
            'error': f'Failed after {max_attempts} attempts due to persistent errors'
        }
    
    def _process_pdf_single_attempt(self, pdf_path, pdf_hash):
        """Single attempt to process PDF"""
        try:
            # Use timestamp to ensure unique index names
            timestamp = int(time.time())
            index_name = f"pdf-{pdf_hash}-{timestamp}"
            print(f"Processing with unique index: {index_name}")
            
            # Step 1: Load and validate PDF
            print("Step 1: Loading PDF document...")
            try:
                loader = DoclingLoader(file_path=[pdf_path], export_type=ExportType.DOC_CHUNKS)
                docs = loader.load()
                
                if not docs:
                    return {
                        'success': False,
                        'error': 'No content could be extracted from the PDF. Please check if the PDF is readable.'
                    }
                
                print(f"Successfully loaded {len(docs)} document chunks")
                
            except Exception as load_error:
                return {
                    'success': False,
                    'error': f'Failed to load PDF document: {str(load_error)}'
                }
            
            # Step 2: Split documents
            print("Step 2: Splitting documents into chunks...")
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                separators=["\n\n", "\n", " ", ""]
            )
            split_docs = text_splitter.split_documents(docs)
            
            if not split_docs:
                return {
                    'success': False,
                    'error': 'No text chunks could be created from the PDF content.'
                }
            
            print(f"Created {len(split_docs)} text chunks")
            
            # Step 3: Sanitize metadata
            print("Step 3: Sanitizing document metadata...")
            def sanitize_metadata(doc):
                clean_meta = {
                    "pdf_hash": pdf_hash,
                    "pdf_name": os.path.basename(pdf_path),
                    "chunk_id": str(uuid.uuid4())[:8]
                }
                
                try:
                    for k, v in doc.metadata.items():
                        if k == "dl_meta":
                            clean_meta[k] = json.dumps(v)[:800] if v else ""
                        elif isinstance(v, (str, int, float, bool)):
                            if isinstance(v, str) and len(v) > 500:
                                clean_meta[k] = v[:500] + "..."
                            else:
                                clean_meta[k] = v
                        elif isinstance(v, list) and all(isinstance(i, str) for i in v):
                            clean_meta[k] = v[:10]  # Limit list size
                        else:
                            clean_meta[k] = str(v)[:300] if v else ""
                except Exception as e:
                    print(f"Warning: Error processing metadata: {e}")
                
                doc.metadata = clean_meta
                return doc
            
            split_docs = [sanitize_metadata(doc) for doc in split_docs]
            
            # Step 4: Create Pinecone index with enhanced error handling
            print("Step 4: Creating Pinecone index...")
            
            # Clean up any existing index first
            self.cleanup_existing_index(index_name)
            
            try:
                print(f"Creating new index: {index_name}")
                self.pc.create_index(
                    name=index_name,
                    dimension=1024,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
                
                # Wait for index to be ready with proper timeout
                print("Waiting for index to be ready...")
                max_wait = 300  # 5 minutes
                start_time = time.time()
                
                while time.time() - start_time < max_wait:
                    try:
                        index_stats = self.pc.describe_index(index_name)
                        if index_stats.status['ready']:
                            print("Index is ready!")
                            break
                    except Exception as check_error:
                        print(f"Index status check error (retrying): {check_error}")
                    
                    time.sleep(10)
                else:
                    raise Exception(f"Index creation timeout after {max_wait} seconds")
                
            except Exception as index_error:
                return {
                    'success': False,
                    'error': f'Failed to create Pinecone index: {str(index_error)}'
                }
            
            # Step 5: Create vectorstore with retry logic
            print("Step 5: Creating vectorstore...")
            vectorstore_attempts = 3
            
            for vs_attempt in range(vectorstore_attempts):
                try:
                    print(f"Vectorstore creation attempt {vs_attempt + 1}/{vectorstore_attempts}")
                    
                    vectorstore = PineconeVectorStore.from_documents(
                        documents=split_docs,
                        embedding=self.embeddings,
                        index_name=index_name
                    )
                    
                    # Verify vectorstore is working
                    test_query = vectorstore.similarity_search("test", k=1)
                    
                    # Store vectorstore for future use
                    self.vectorstores[pdf_hash] = vectorstore
                    
                    print("Vectorstore created and verified successfully!")
                    return {
                        'success': True,
                        'chunk_count': len(split_docs),
                        'index_name': index_name
                    }
                    
                except Exception as vs_error:
                    print(f"Vectorstore attempt {vs_attempt + 1} failed: {vs_error}")
                    if vs_attempt == vectorstore_attempts - 1:
                        return {
                            'success': False,
                            'error': f'Failed to create vectorstore after {vectorstore_attempts} attempts: {str(vs_error)}'
                        }
                    time.sleep(15)  # Wait before retry
            
        except Exception as e:
            print(f"Processing error: {str(e)}")
            traceback.print_exc()
            return {
                'success': False,
                'error': f"Processing failed: {str(e)}"
            }
    
    def process_pdf(self, pdf_path, pdf_hash):
        """Main process_pdf method with comprehensive error handling"""
        try:
            print(f"=== STARTING PDF PROCESSING ===")
            print(f"PDF Path: {pdf_path}")
            print(f"PDF Hash: {pdf_hash}")
            
            # Check if already processed
            if self.is_pdf_processed(pdf_hash):
                print("PDF already processed, loading existing vectorstore...")
                
                # Find the existing index
                all_indexes = self.pc.list_indexes()
                matching_index = None
                
                for index_info in all_indexes:
                    if index_info['name'].startswith(f"pdf-{pdf_hash}"):
                        matching_index = index_info['name']
                        break
                
                if matching_index:
                    try:
                        vectorstore = PineconeVectorStore(
                            index_name=matching_index,
                            embedding=self.embeddings
                        )
                        self.vectorstores[pdf_hash] = vectorstore
                        return {
                            'success': True,
                            'message': 'PDF already processed',
                            'chunk_count': 0,
                            'is_existing': True
                        }
                    except Exception as e:
                        print(f"Error loading existing vectorstore: {e}")
                        print("Proceeding with new processing...")
            
            # Process with exponential backoff
            result = self.process_pdf_with_exponential_backoff(pdf_path, pdf_hash)
            
            if result['success']:
                print("=== PROCESSING COMPLETED SUCCESSFULLY ===")
            else:
                print(f"=== PROCESSING FAILED: {result['error']} ===")
            
            return result
            
        except Exception as e:
            print(f"Critical processing error: {str(e)}")
            traceback.print_exc()
            return {
                'success': False,
                'error': f"Critical processing failure: {str(e)}"
            }
    
    def get_answer(self, pdf_hash, question):
        """Get answer for a question with enhanced error handling"""
        try:
            print(f"Getting answer for PDF hash: {pdf_hash}")
            
            # Get vectorstore
            if pdf_hash not in self.vectorstores:
                print("Vectorstore not in memory, searching for existing index...")
                
                # Try to find the index with the hash prefix
                all_indexes = self.pc.list_indexes()
                matching_index = None
                
                for index_info in all_indexes:
                    if index_info['name'].startswith(f"pdf-{pdf_hash}"):
                        matching_index = index_info['name']
                        print(f"Found matching index: {matching_index}")
                        break
                
                if not matching_index:
                    return {
                        'success': False,
                        'error': 'PDF not processed or index not found. Please upload and process the PDF first.'
                    }
                
                try:
                    self.vectorstores[pdf_hash] = PineconeVectorStore(
                        index_name=matching_index,
                        embedding=self.embeddings
                    )
                except Exception as vs_error:
                    return {
                        'success': False,
                        'error': f'Failed to load vectorstore: {str(vs_error)}'
                    }
            
            vectorstore = self.vectorstores[pdf_hash]
            
            # Enhanced prompt for better formatting
            prompt = ChatPromptTemplate.from_template("""
You are an expert insurance advisor specializing in different Insurance Domains. Provide responses that are visually appealing, scannable, and engaging using these formatting rules:

**Formatting Requirements:**
1. **Structure:** Organize answers in this sequence:
   🛡️ **Core Answer** (1-2 sentence summary)
   🔍 **Key Details** (bulleted specifics)
   ⚠️ **Important Conditions** (warning symbols for limitations)
   💡 **Pro Tips** (actionable advice with lightbulb icon)
   📜 **Document Reference** (page citations)

2. **Visual Elements:**
   - Use relevant emojis in section headers (see examples below)
   - Highlight **key terms** and **numbers** in bold
   - For lists: → for features, ⚠️ for exclusions, ✅ for requirements
   - Always include page references (📄 Page X)

3. **Content Rules:**
   - Start with direct yes/no when applicable
   - Keep sentences under 15 words
   - Use insurance terms from context (don't simplify jargon)
   - Add 1 pro tip even if not asked
   - Never invent details - say "Not specified in documents" when unclear

**Response Template:**
🛡️ [Concise 1-sentence answer with emoji]

🔍 **Coverage Details:**
→ [Feature 1] 
→ [Feature 2] 
→ [Limit: **₹Amount**] (📄 Page X)

⚠️ **Key Limitations:**
⚠️ [Exclusion 1]
⚠️ [Exclusion 2] (📄 Page Y)

💡 **Pro Tip:** [Actionable advice]

📜 **Policy Reference:** Sections [X], [Y]

**Context:** {context}
**Question:** {input}
""")
            
            try:
                document_chain = create_stuff_documents_chain(self.llm, prompt)
                retrieval_chain = create_retrieval_chain(vectorstore.as_retriever(search_kwargs={"k": 5}), document_chain)
                
                # Get response with timeout handling
                response = retrieval_chain.invoke({"input": question})
                
                # Extract source information
                sources = []
                if 'context' in response:
                    for doc in response['context'][:3]:
                        sources.append({
                            'content': doc.page_content[:200] + "...",
                            'metadata': doc.metadata
                        })
                
                return {
                    'success': True,
                    'answer': response['answer'],
                    'sources': sources
                }
                
            except Exception as chain_error:
                return {
                    'success': False,
                    'error': f'Failed to generate answer: {str(chain_error)}'
                }
            
        except Exception as e:
            print(f"Answer generation error: {str(e)}")
            traceback.print_exc()
            return {
                'success': False,
                'error': f"Failed to generate answer: {str(e)}"
            }

