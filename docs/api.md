# API Contract

## Card

```ts
type CardType = "image" | "text";
type AiStatus = "pending" | "generating" | "done" | "failed";

type InspirationCard = {
  id: string;
  weekKey: string;
  type: CardType;
  textContent?: string;
  imageUrl?: string;
  summary?: string;
  keywords: string[];
  x: number;
  y: number;
  width: number;
  rotation: number;
  styleSeed: string;
  aiStatus: AiStatus;
  aiError?: string;
  createdAt: string;
  updatedAt: string;
};
```

## Endpoints

- `GET /api/weeks/{weekKey}/cards`
- `POST /api/cards/text`
- `POST /api/cards/image`
- `PATCH /api/cards/{id}`
- `POST /api/cards/{id}/analyze`
- `DELETE /api/cards/{id}`
