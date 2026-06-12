from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate, validates_schema

_VALID_LLM_PROVIDERS = ["ollama", "openai", "anthropic"]
_VALID_EMB_PROVIDERS = ["ollama", "openai"]


class LLMConfigUpdateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    provider = fields.String(
        required=True,
        validate=validate.OneOf(_VALID_LLM_PROVIDERS, error="Must be one of: ollama, openai, anthropic"),
    )
    model_name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    temperature = fields.Float(load_default=0.0, validate=validate.Range(min=0.0, max=2.0))
    # api_key is accepted on write but never returned in GET responses
    api_key = fields.String(load_default=None, allow_none=True)
    system_prompt = fields.String(load_default=None, allow_none=True)


class EmbeddingConfigUpdateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    provider = fields.String(
        required=True,
        validate=validate.OneOf(_VALID_EMB_PROVIDERS, error="Must be one of: ollama, openai"),
    )
    model_name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    api_key = fields.String(load_default=None, allow_none=True)


class ChunkConfigUpdateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    chunk_size = fields.Integer(required=True, validate=validate.Range(min=100, max=10000))
    chunk_overlap = fields.Integer(required=True, validate=validate.Range(min=0))
    k_retrievals = fields.Integer(required=True, validate=validate.Range(min=1, max=50))

    @validates_schema
    def validate_overlap_less_than_size(self, data, **kwargs):
        size = data.get("chunk_size")
        overlap = data.get("chunk_overlap")
        if size is not None and overlap is not None and overlap >= size:
            raise ValidationError(
                "chunk_overlap must be less than chunk_size.",
                field_name="chunk_overlap",
            )


class SourceConfigCreateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    url = fields.String(required=True, validate=[
        validate.Length(min=10, max=500),
        validate.URL(error="Must be a valid URL."),
    ])
    active = fields.Boolean(load_default=True)


class SourceConfigUpdateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.String(validate=validate.Length(min=1, max=100))
    url = fields.String(validate=[
        validate.Length(min=10, max=500),
        validate.URL(error="Must be a valid URL."),
    ])
    active = fields.Boolean()
