import streamlit as st

app_page = st.Page(page="app.py", title="Doc Verify")
compliance_page = st.Page(page="pages/compliance.py", title="Report Gen")

pg = st.navigation(
    pages=[app_page, compliance_page]
)

pg.run()
