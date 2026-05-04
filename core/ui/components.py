import streamlit as st
import yaml
from pathlib import Path
from core.ai.role_expander import expand_roles

def render_role_expander(config_key="roles_text"):
    """
    Render a global, reusable AI Role Expander component.
    Updates st.session_state[config_key] with expanded roles.
    """
    # Load existing config for defaults if not in session state
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    default_roles = "\n".join(config.get("search", {}).get("roles", ["Software Engineer"]))
    
    if config_key not in st.session_state:
        st.session_state[config_key] = default_roles

    with st.expander("🤖 AI Role Variant Generator", expanded=False):
        st.markdown("### Broaden Your Search")
        st.write("Use AI to find similar job titles and broaden your search coverage.")
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Use a temporary key for the text area inside the expander to avoid direct state conflict
        current_roles = st.text_area(
            "Current Target Roles",
            value=st.session_state[config_key],
            height=150,
            key=f"{config_key}_expander_input",
            help="The roles you are currently targeting. AI will expand from these."
        )

        exp_col1, exp_col2 = st.columns([2, 1])
        with exp_col1:
            expand_base_role = st.text_input(
                "Specific Role to Variant (Optional)",
                value="",
                placeholder="e.g. Data Scientist",
                key=f"{config_key}_base_role",
                help="If provided, AI will only expand this specific title."
            )
        with exp_col2:
            expand_exp = st.number_input(
                "Target Seniority (yrs)",
                value=config.get("search", {}).get("experience_years", 3),
                min_value=0,
                key=f"{config_key}_exp_input",
            )

        if st.button("Generate Variants", key=f"{config_key}_gen_btn", use_container_width=True):
            base_roles = [expand_base_role.strip()] if expand_base_role.strip() else [r.strip() for r in current_roles.split("\n") if r.strip()]
            
            if base_roles:
                with st.status("Expanding roles...", expanded=True) as status:
                    all_expanded = []
                    for role in base_roles:
                        status.write(f"Analyzing variants for: {role}")
                        try:
                            expanded = expand_roles(role, int(expand_exp))
                            all_expanded.extend(expanded)
                        except Exception as e:
                            status.write(f"⚠️ Error expanding {role}: {e}")
                    
                    existing = [r.strip() for r in current_roles.split("\n") if r.strip()]
                    unique_expanded = [r for r in all_expanded if r not in existing]
                    
                    merged = existing + unique_expanded
                    st.session_state[config_key] = "\n".join(merged)
                    status.update(label=f"Added {len(unique_expanded)} variants!", state="complete")
                st.rerun()
    
    return st.session_state[config_key]
