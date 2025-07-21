# rag_logic.py

import os
import re
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
from langchain.schema import Document

def extract_issue_number(filename):
    """파일명에서 호수를 추출하는 함수"""
    pattern = r'제(\d+)호'
    match = re.search(pattern, filename)
    if match:
        return match.group(1)
    return "Unknown"

def initialize_rag_chain(openai_api_key, pdf_paths, file_names=None):
    """OpenAI API 키와 PDF 파일 경로 리스트를 받아 RAG 체인을 초기화합니다."""
    print("--- RAG 파이프라인 초기화 시작 ---")
    
    # API 키 유효성 검사
    if not openai_api_key or not openai_api_key.startswith('sk-'):
        raise ValueError("유효한 OpenAI API 키를 입력해주세요.")
    
    all_docs = []
    
    # 모든 PDF 파일을 순회하며 문서 로드
    for i, pdf_path in enumerate(pdf_paths):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
        
        try:
            loader = PyPDFLoader(pdf_path)
            docs = loader.load()
            
            # 파일명에서 호수 추출
            if file_names and i < len(file_names):
                filename = file_names[i]
                issue_number = extract_issue_number(filename)
            else:
                filename = f"Document_{i+1}"
                issue_number = str(i+1)
            
            # 각 문서에 풍부한 메타데이터 추가
            for doc_idx, doc in enumerate(docs):
                doc.metadata['file_index'] = i
                doc.metadata['document_id'] = i
                doc.metadata['file_name'] = filename
                doc.metadata['document_name'] = filename
                                
                # 페이지 번호 정보 추가
                original_page = doc.metadata.get('page', doc_idx)
                page_num = original_page + 1
                doc.metadata['page_number'] = page_num
                
                # 정확한 출처 정보 생성
                base_filename = os.path.splitext(filename)[0]  # 확장자 제거
                doc.metadata['source_info'] = f"{base_filename}의 {page_num}p"
                print(f"메타데이터 추가: {doc.metadata['source_info']}")
            
            all_docs.extend(docs)
            print(f"✅ 파일 {i+1} 로드 완료 - {len(docs)}페이지")
            
        except Exception as e:
            print(f"❌ 파일 {i+1} 로드 실패: {str(e)}")
            raise e
    
    print(f"✅ [1/5] 전체 문서 로드 완료 - 총 {len(all_docs)}페이지")
    
    # 문서가 비어있는지 확인
    if not all_docs:
        raise ValueError("PDF 문서들이 비어있거나 텍스트를 추출할 수 없습니다.")
    
    # 문서 내용 길이 확인
    total_text = ""
    for doc in all_docs:
        total_text += doc.page_content
    
    print(f"전체 텍스트 길이: {len(total_text)} 문자")
    
    if len(total_text.strip()) < 100:
        raise ValueError("문서 내용이 너무 짧습니다. 스캔된 이미지 PDF일 가능성이 있습니다.")
    
    try:
        # 2. 문서 분할 - 더 작은 청크로 분할
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,  # 청크 크기 조정
            chunk_overlap=50,  # 오버랩 조정
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""],
            length_function=len
        )
        
        splits = text_splitter.split_documents(all_docs)
        
        # 분할된 청크의 메타데이터 확인 및 보정
        for split in splits:
            if 'source_info' not in split.metadata:
                file_name = split.metadata.get('file_name', 'Unknown')
                base_filename = os.path.splitext(file_name)[0]
                page_num = split.metadata.get('page_number', 'Unknown')
                split.metadata['source_info'] = f"{base_filename}의 {page_num}p"
            
            # 청크 내용 미리보기 추가
            split.metadata['content_preview'] = split.page_content[:100] + "..." if len(split.page_content) > 100 else split.page_content
        
        print(f"✅ [2/5] 문서 분할 완료 - 총 {len(splits)}개 청크")
        
        if not splits:
            raise ValueError("문서 분할 결과가 비어있습니다.")
        
        # 3. OpenAI 임베딩 및 벡터 DB 설정
        embeddings = OpenAIEmbeddings(
            openai_api_key=openai_api_key,
            model="text-embedding-3-small"
        )
        
        vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)
        print("✅ [3/5] FAISS 벡터 DB 생성 완료")
        
        # 4. 검색기 생성
        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 10}  # 검색 결과 수 조정
        )
        print("✅ [4/5] 검색기 생성 완료")
        
        # 5. OpenAI LLM 설정
        template = """당신은 해당 분야의 전문가입니다. 주어진 문맥(context)을 바탕으로 질문에 답변해주세요.

**답변 지침:**
1. 문맥에서 질문과 관련된 모든 정보를 찾아서 구체적으로 그리고 두괄식으로 답변하세요
2. 여러 문서에서 관련 정보를 찾은 경우, 모든 정보를 통합하여 답변하세요
3. 답변할 때는 반드시 업로드 된 문서를 기준으로 출처를 명시하세요
4. 질문과 관련된 정보가 직접 언급되지 않아도 관련된 내용이나 유사한 정보가 있다면 참고하여 답변하세요
5. 문맥에서 직접적인 답변을 찾을 수 없는 경우에만 "해당 문서들에는 구체적인 정보가 포함되어 있지 않습니다"라고 답변하세요

**문맥 정보:**
{context}

**질문:** {question}

**답변:**"""
        
        prompt = ChatPromptTemplate.from_template(template)
        
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            openai_api_key=openai_api_key,
            max_tokens=1000,
            timeout=60  # 타임아웃 증가
        )
        
        def format_docs(docs):
            """문서들을 출처 정보와 함께 포맷팅"""
            if not docs:
                return "검색된 문서가 없습니다."
            
            formatted = []
            for i, doc in enumerate(docs):
                source = doc.metadata.get('source_info', 'Unknown')
                content = doc.page_content
                print(f"포맷팅 중인 문서 {i+1}: {source}")
                formatted.append(f"[출처: {source}]\n{content}")
            
            return "\n\n".join(formatted)
        
        rag_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        
        print("✅ [5/5] RAG 체인 생성 완료")
        
        return rag_chain, retriever, openai_api_key
        
    except Exception as e:
        print(f"❌ RAG 초기화 중 오류 발생: {str(e)}")
        raise e

def get_answer(chain, retriever, question, openai_api_key):
    """RAG 체인과 검색기를 이용하여 답변을 생성합니다."""
    try:
        print(f"질문: {question}")
        
        # 검색 수행
        docs = retriever.get_relevant_documents(question)
        print(f"검색된 문서 개수: {len(docs)}")
        
        if not docs:
            return "해당 문서들에는 관련 정보가 포함되어 있지 않습니다."
        
        # 검색된 문서들 확인
        valid_docs = []
        for i, doc in enumerate(docs):
            source_info = doc.metadata.get('source_info', 'Unknown')
            print(f"문서 {i+1} 출처: {source_info}")
            print(f"내용 미리보기: {doc.page_content[:100]}...")
            valid_docs.append(doc)
        
        if not valid_docs:
            return "문서에서 관련 정보를 찾을 수 없습니다."
        
        print(f"유효한 문서 개수: {len(valid_docs)}")
        
        # 상위 문서들로 컨텍스트 생성
        def format_docs_for_context(docs):
            formatted = []
            for doc in docs:
                source = doc.metadata.get('source_info', 'Unknown')
                content = doc.page_content
                formatted.append(f"[출처: {source}]\n{content}")
            return "\n\n".join(formatted)
        
        context = format_docs_for_context(valid_docs[:8])  # 상위 8개 문서만 사용
        
        # 프롬프트 구성
        prompt_text = f"""당신은 해당 분야의 전문가입니다. 주어진 문맥(context)을 바탕으로 질문에 답변해주세요.

**답변 지침:**
1. 문맥에서 질문과 관련된 모든 정보를 찾아서 구체적으로 그리고 두괄식으로 답변하세요
2. 여러 문서에서 관련 정보를 찾은 경우, 모든 정보를 통합하여 답변하세요
3. 답변할 때는 반드시 업로드 된 문서를 기준으로 출처를 명시하세요
4. 질문과 관련된 정보가 직접 언급되지 않아도 관련된 내용이나 유사한 정보가 있다면 참고하여 답변하세요
5. 문맥에서 직접적인 답변을 찾을 수 없는 경우에만 "해당 문서들에는 구체적인 정보가 포함되어 있지 않습니다"라고 답변하세요

**문맥 정보:**
{context}

**질문:** {question}

**답변:**"""
        
        # LLM 직접 호출
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            openai_api_key=openai_api_key,
            max_tokens=1000,
            timeout=60
        )
        
        response = llm.invoke(prompt_text)
        return response.content
        
    except Exception as e:
        print(f"상세 오류 정보: {str(e)}")
        return f"답변 생성 중 오류가 발생했습니다: {str(e)}"