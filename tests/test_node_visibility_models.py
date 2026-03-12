"""Tests for node visibility database model and migration changes."""

import pytest
from sqlalchemy import text
from app.db.models import NodeModel
from app.db.migrate import ensure_schema, _table_cols
from app.db.session import init_engine


@pytest.fixture
def db_engine(tmp_path, monkeypatch):
    """Create a test database engine."""
    db_file = tmp_path / "test_visibility.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    engine = init_engine()
    ensure_schema(engine)
    return engine


class TestNodeModelVisibility:
    """Test NodeModel visible field integration."""
    
    def test_node_model_has_visible_field(self, db_engine):
        """Test that NodeModel includes visible field with correct default."""
        # Check table schema includes visible column
        with db_engine.connect() as conn:
            cols = _table_cols(conn, "nodes")
            assert "visible" in cols
    
    def test_node_model_to_dict_includes_visible(self, db_engine):
        """Test that to_dict() includes visible field."""
        from sqlalchemy.orm import Session
        
        with Session(db_engine) as session:
            node = NodeModel(
                id="test_node_1",
                name="Test Node",
                type="sensor",
                category="sensor",
                enabled=True,
                visible=True,
                config_json='{"test": "value"}',
                x=100.0,
                y=200.0
            )
            session.add(node)
            session.commit()
            
            # Test to_dict includes visible field
            result = node.to_dict()
            assert "visible" in result
            assert result["visible"] is True
    
    def test_node_model_visible_defaults_true(self, db_engine):
        """Test that visible field defaults to True."""
        from sqlalchemy.orm import Session
        
        with Session(db_engine) as session:
            node = NodeModel(
                id="test_node_2",
                name="Test Node 2",
                type="sensor",
                category="sensor",
                enabled=True,
                # Not setting visible explicitly
                config_json='{}',
                x=100.0,
                y=200.0
            )
            session.add(node)
            session.commit()
            session.refresh(node)
            
            assert node.visible is True
    
    def test_migration_visible_column_added(self, db_engine):
        """Test that migration properly adds visible column."""
        with db_engine.connect() as conn:
            # Check column exists and has correct default
            result = conn.execute(text("PRAGMA table_info(nodes)")).fetchall()
            visible_col = next((col for col in result if col[1] == "visible"), None)
            assert visible_col is not None
            # Column info: (cid, name, type, notnull, dflt_value, pk)
            assert visible_col[4] in ("1", "'1'")  # Default value should be 1 (True) - SQLite may quote it
    
    def test_migration_idempotent(self, db_engine):
        """Test that running migration twice doesn't cause errors."""
        # This should not raise any exceptions
        ensure_schema(db_engine)
        ensure_schema(db_engine)  # Run again
        
        with db_engine.connect() as conn:
            cols = _table_cols(conn, "nodes")
            assert "visible" in cols


class TestVisibilityMigrationEdgeCases:
    """Test edge cases for the visibility migration."""
    
    def test_existing_nodes_get_visible_true(self, db_engine):
        """Test that existing nodes without visible get default True."""
        from sqlalchemy.orm import Session
        
        with Session(db_engine) as session:
            # Insert node using raw SQL to simulate pre-migration state
            session.execute(text("""
                INSERT INTO nodes (id, name, type, category, enabled, config, x, y)
                VALUES ('legacy_node', 'Legacy Node', 'sensor', 'sensor', 1, '{}', 100.0, 200.0)
            """))
            session.commit()
            
            # Now query using ORM - should have visible=True from server default
            node = session.query(NodeModel).filter(NodeModel.id == "legacy_node").first()
            assert node.visible is True
    
    def test_visible_false_persists(self, db_engine):
        """Test that visible=False can be set and persists correctly."""
        from sqlalchemy.orm import Session
        
        with Session(db_engine) as session:
            node = NodeModel(
                id="invisible_node",
                name="Invisible Node",
                type="sensor",
                category="sensor",
                enabled=True,
                visible=False,  # Explicitly set to False
                config_json='{}',
                x=100.0,
                y=200.0
            )
            session.add(node)
            session.commit()
            session.refresh(node)
            
            assert node.visible is False
            
            # Verify it persists across sessions
            session.close()
            
        with Session(db_engine) as new_session:
            retrieved = new_session.query(NodeModel).filter(NodeModel.id == "invisible_node").first()
            assert retrieved.visible is False