import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#1b4d3e",
    },
    secondary: {
      main: "#8a4b2a",
    },
    background: {
      default: "#f6f7f4",
      paper: "#ffffff",
    },
    text: {
      primary: "#1d2521",
      secondary: "#56625d",
    },
  },
  shape: {
    borderRadius: 8,
  },
  typography: {
    fontFamily:
      "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    h4: {
      fontWeight: 700,
    },
    h6: {
      fontWeight: 700,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 700,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: "0 1px 3px rgba(29, 37, 33, 0.08)",
        },
      },
    },
  },
});
