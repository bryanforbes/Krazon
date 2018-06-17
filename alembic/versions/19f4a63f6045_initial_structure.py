"""Initial structure

Revision ID: 19f4a63f6045
Revises: 
Create Date: 2018-06-17 14:19:17.336396

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '19f4a63f6045'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('clips',
                    sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
                    sa.Column('name', sa.String),
                    sa.Column('member_id', sa.String),
                    sa.Column('filename', sa.String))

    op.create_index('clips_member_id_idx', 'clips', ['member_id'])
    op.create_index('clips_member_id_name_idx', 'clips', ['member_id', 'name'])


def downgrade():
    op.drop_index('clips_member_id_name_idx')
    op.drop_index('clips_member_id_idx')
    op.drop_table('clips')
