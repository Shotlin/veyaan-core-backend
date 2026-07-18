"""Add state transition constraints for commands using triggers

Revision ID: 007
Revises: 006
Create Date: 2024-01-18 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the state transition validation function and trigger
    # Using string comparisons instead of enum type
    op.execute("""
        CREATE OR REPLACE FUNCTION validate_command_state_transition()
        RETURNS trigger AS $$
        DECLARE
            old_state text;
            new_state text;
        BEGIN
            -- Get old and new states
            old_state := OLD.state;
            new_state := NEW.state;

            -- If state hasn't changed, allow
            IF old_state = new_state THEN
                RETURN NEW;
            END IF;

            -- Validate state transition based on old_state -> new_state
            CASE old_state
                WHEN 'received' THEN
                    IF new_state NOT IN ('validated', 'awaiting_approval', 'queued', 'cancelled') THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'validated' THEN
                    IF new_state NOT IN ('awaiting_approval', 'queued', 'cancelled') THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'awaiting_approval' THEN
                    IF new_state NOT IN ('approved', 'rejected', 'expired', 'cancelled') THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'approved' THEN
                    IF new_state NOT IN ('queued', 'cancelled') THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'rejected' THEN
                    IF new_state != 'rejected' THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'queued' THEN
                    IF new_state NOT IN ('delivered', 'expired', 'cancelled', 'blocked_by_emergency_stop') THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'delivered' THEN
                    IF new_state NOT IN ('acknowledged', 'expired', 'cancelled') THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'acknowledged' THEN
                    IF new_state NOT IN ('running', 'expired', 'cancelled') THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'running' THEN
                    IF new_state NOT IN ('succeeded', 'failed', 'cancelled', 'timed_out') THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'succeeded' THEN
                    IF new_state != 'succeeded' THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'failed' THEN
                    IF new_state != 'failed' THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'timed_out' THEN
                    IF new_state != 'timed_out' THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'cancelled' THEN
                    IF new_state != 'cancelled' THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'expired' THEN
                    IF new_state != 'expired' THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                WHEN 'blocked_by_emergency_stop' THEN
                    IF new_state NOT IN ('queued', 'cancelled') THEN
                        RAISE EXCEPTION 'Invalid state transition from % to %', old_state, new_state;
                    END IF;

                ELSE
                    RAISE EXCEPTION 'Unknown old state: %', old_state;
            END CASE;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger on commands table
    op.execute("""
        CREATE TRIGGER trg_validate_command_state_transition
        BEFORE UPDATE OF state ON commands
        FOR EACH ROW
        EXECUTE FUNCTION validate_command_state_transition();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS validate_command_state_transition ON commands;")
    op.execute("DROP FUNCTION IF EXISTS validate_command_state_transition();")
