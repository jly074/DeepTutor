import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import QuestionSource from "@/components/space/question-bank/QuestionSource";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (value: string) => value }),
}));

it("displays supplied source labels without inventing missing values", () => {
  const { rerender } = render(
    <QuestionSource source={{ filename: "synthetic.pdf", pdf_page: 3, question_number: "12(b)" }} />,
  );
  expect(screen.getByText("synthetic.pdf")).toBeVisible();
  expect(screen.getByText("3")).toBeVisible();
  expect(screen.getByText("12(b)")).toBeVisible();
  expect(screen.getAllByText("Unknown")).toHaveLength(1);
  rerender(<QuestionSource source={{ filename: "synthetic.pdf", year: 2024 }} />);
  expect(screen.getByText("2024")).toBeVisible();
});

it("renders legacy entries with no source as unknown", () => {
  render(<QuestionSource />);
  expect(screen.getAllByText("Unknown")).toHaveLength(4);
});
