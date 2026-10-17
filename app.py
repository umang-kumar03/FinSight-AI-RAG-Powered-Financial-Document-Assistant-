import streamlit as st

st.set_page_config(
    page_title="FinSight AI",
    page_icon="📊",
    layout="wide",
)

st.title("📊 FinSight AI")
st.subheader("RAG-Powered Financial Document Assistant")

st.write(
    "Explore financial documents and build optimized portfolios."
)

st.divider()

left, right = st.columns(2)

with left:
    st.header("📄 Document Assistant")
    st.write(
        "Ask questions about financial documents "
        "and get answers with sources."
    )
    st.info("Document upload and Q&A will be added next.")

with right:
    st.header("📈 Portfolio Optimizer")
    st.write(
        "Build maximum-Sharpe and minimum-variance portfolios "
        "using historical asset prices."
    )
    st.info("Portfolio optimization will be added later.")

st.divider()
st.caption("For learning and research. Not financial advice.")